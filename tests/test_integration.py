"""
GoldClaw 集成测试 — 切片 8

模拟完整交易生命周期，测试跨模块协作：
- 数据库 + 投资者模块 + 通信层 + 状态机 + 价格历史
- 不测试 Engine.run_tick()（依赖全局 settings），
  而是手动编排引擎 tick 的各个步骤。
"""

import json
import pytest
import sqlite3

from internal.db.connection import get_connection
from internal.db.migrations import run_migrations, seed_initial_data
from internal.db.repository import InvestorRepository
from internal.exchange.schema import InvestorInstruction, OrderFile, StateReport
from internal.exchange.validator import (
    validate_orders,
    record_violation,
    check_hallucination,
    get_unacknowledged_violations,
)
from internal.exchange.webhook_client import build_state_report, write_state_file
from internal.investor.investor_a import InvestorA
from internal.investor.investor_b import InvestorB
from internal.price.history import PriceHistory
from internal.price.volatility import calc_slope, calc_volatility
from internal.state_machine.machine import StateMachine
from internal.state_machine.states import SystemState


@pytest.fixture
def db() -> sqlite3.Connection:
    """内存数据库，初始化两个投资者。"""
    conn = get_connection(":memory:")
    run_migrations(conn)
    seed_initial_data(conn, {"A": 10000.0, "B": 10000.0})
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def inv_a(db: sqlite3.Connection) -> InvestorA:
    return InvestorA(db)


@pytest.fixture
def inv_b(db: sqlite3.Connection) -> InvestorB:
    return InvestorB(db)


@pytest.fixture
def sm() -> StateMachine:
    """状态机（阈值设小便于测试）。"""
    return StateMachine(
        threshold_a=0.001,
        threshold_b=0.001,
        watch_duration=5,
        trigger_slope=0.002,
        silence_period=3,
    )


# ============================================================
# 1. 完整做多生命周期
# ============================================================


class TestFullLifecycleCFDLong:
    """投资者 A：CFD 做多完整生命周期。"""

    def test_open_monitor_tp_close(self, inv_a: InvestorA, db: sqlite3.Connection) -> None:
        """
        开仓 → 价格上涨 → 盈利 → 触及 TP → 自动平仓。
        验证：DB 状态、trade_history 记录、盈亏数值。
        """
        entry_price = 4700.0

        # Step 1: 模拟 OpenClaw 指令 → 开仓
        with db:
            inv_a.open_position(
                price=entry_price,
                margin_pct=0.8,
                action="cfd_long",
                tp=4800.0,
                sl=4600.0,
            )

        s = inv_a.state
        assert s["current_action"] == "cfd_long"
        assert s["entry_price"] == entry_price
        assert s["tp"] == 4800.0
        assert s["sl"] == 4600.0
        # margin=8000, spread=80, actual_margin=7920
        assert s["margin_committed"] == pytest.approx(7920.0)
        assert s["cash"] == pytest.approx(2000.0)

        # Step 2: 价格上涨到 4750
        with db:
            inv_a.update_pnl(4750.0)

        s = inv_a.state
        assert s["nominal_pnl"] > 0
        assert s["total_assets"] > 10000.0

        # Step 3: TP 未触发
        assert inv_a.check_tp_sl(4790.0) is None

        # Step 4: 价格触及 TP → 自动平仓
        assert inv_a.check_tp_sl(4800.0) == "take_profit"
        with db:
            result = inv_a.close_position(4800.0, reason="take_profit")

        # Step 5: 验证平仓后状态
        s = inv_a.state
        assert s["current_action"] == "idle"
        assert s["margin_committed"] == pytest.approx(0.0)
        assert s["cash"] > 10000.0  # 盈利
        assert s["nominal_pnl"] == pytest.approx(0.0)

        # Step 6: 验证 trade_history 有记录
        repo = InvestorRepository(db)
        trades = db.execute(
            "SELECT * FROM trade_history WHERE investor_id='A' ORDER BY id"
        ).fetchall()
        assert len(trades) >= 2  # 开仓 + 平仓

        # 开仓记录
        assert trades[0]["action"] == "cfd_long"
        assert trades[0]["gold_price"] == pytest.approx(entry_price)

        # 平仓记录
        assert trades[-1]["action"] == "close"
        assert trades[-1]["trigger_reason"] == "take_profit"
        assert trades[-1]["gold_price"] == pytest.approx(4800.0)


# ============================================================
# 2. 完整做空生命周期
# ============================================================


class TestFullLifecycleCFDShort:
    """投资者 B：CFD 做空完整生命周期。"""

    def test_short_profit_then_sl(self, inv_b: InvestorB, db: sqlite3.Connection) -> None:
        """
        B 做空 → 价格下跌盈利 → 反弹触及 SL → 止损平仓。
        """
        entry_price = 4700.0

        # Step 1: B 开 CFD 做空
        with db:
            inv_b.open_position(
                price=entry_price,
                margin_pct=0.6,
                action="cfd_short",
                tp=4600.0,
                sl=4750.0,
            )

        s = inv_b.state
        assert s["current_action"] == "cfd_short"
        # margin=6000, spread=60, actual_margin=5940
        assert s["margin_committed"] == pytest.approx(5940.0)
        assert s["cash"] == pytest.approx(4000.0)

        # Step 2: 价格下跌 → 做空盈利
        with db:
            inv_b.update_pnl(4650.0)

        s = inv_b.state
        assert s["nominal_pnl"] > 0  # 做空盈利
        assert s["total_assets"] > 10000.0

        # Step 3: 价格反弹到 SL → 止损
        assert inv_b.check_tp_sl(4750.0) == "stop_loss"
        with db:
            inv_b.close_position(4750.0, reason="stop_loss")

        # Step 4: 验证
        s = inv_b.state
        assert s["current_action"] == "idle"
        assert s["cash"] < 10000.0  # 止损亏损
        assert s["margin_committed"] == pytest.approx(0.0)

        # trade_history
        trades = db.execute(
            "SELECT * FROM trade_history WHERE investor_id='B' AND trigger_reason='stop_loss'"
        ).fetchall()
        assert len(trades) >= 1


# ============================================================
# 3. SGLN 完整生命周期
# ============================================================


class TestFullLifecycleSGLN:
    """投资者 B：SGLN 做多完整生命周期。"""

    def test_sgln_track_and_close(self, inv_b: InvestorB, db: sqlite3.Connection) -> None:
        """
        B 做 SGLN → 金价上涨跟踪 → 通过 close 指令平仓。
        SGLN 无费用、无 TP/SL。
        """
        entry_price = 4700.0

        # Step 1: SGLN 做多
        with db:
            inv_b.open_position(
                price=entry_price,
                margin_pct=0.5,
                action="sgln_long",
            )

        s = inv_b.state
        assert s["current_action"] == "sgln_long"
        assert s["tp"] == pytest.approx(0.0)
        assert s["sl"] == pytest.approx(0.0)
        # investment = 5000, no spread
        assert s["margin_committed"] == pytest.approx(5000.0)
        assert s["cash"] == pytest.approx(5000.0)

        # Step 2: 金价上涨 → SGLN 盈利
        with db:
            inv_b.update_pnl(4800.0)

        s = inv_b.state
        # SGLN PnL = 5000 × (4800/4700 - 1) ≈ 106.38
        assert s["nominal_pnl"] > 0
        assert s["total_assets"] > 10000.0

        # Step 3: SGLN 无 TP/SL
        assert inv_b.check_tp_sl(5000.0) is None
        assert inv_b.check_tp_sl(4000.0) is None

        # Step 4: 通过指令平仓
        with db:
            result = inv_b.close_position(4800.0, reason="openclaw_instruction")

        s = inv_b.state
        assert s["current_action"] == "idle"
        assert s["cash"] > 10000.0  # SGLN 盈利
        assert s["margin_committed"] == pytest.approx(0.0)

        # Step 5: 验证 trade_history
        trades = db.execute(
            "SELECT * FROM trade_history WHERE investor_id='B' ORDER BY id"
        ).fetchall()
        assert len(trades) >= 2  # 开仓 + 平仓


# ============================================================
# 4. 爆仓紧急流程
# ============================================================


class TestMarginCallLifecycle:
    """投资者 A：爆仓完整流程。"""

    def test_margin_call_auto_close(self, inv_a: InvestorA, db: sqlite3.Connection) -> None:
        """
        A 做多 → 金价暴跌 → 爆仓 → 自动平仓。
        margin_call=1，cash ≥ 0。
        """
        entry_price = 4700.0

        # Step 1: 开仓
        with db:
            inv_a.open_position(
                price=entry_price,
                margin_pct=0.8,
                action="cfd_long",
                tp=4800.0,
                sl=4600.0,
            )

        # Step 2: 金价暴跌 → 爆仓
        # 20x 杠杆：4700→4300 跌幅 8.5%，名义亏损 = 7920×20×(4300-4700)/4700 ≈ -13480
        assert inv_a.check_margin_call(4300.0) is True

        # Step 3: 自动平仓
        with db:
            inv_a.close_position(4300.0, reason="margin_call")

        # Step 4: 验证状态
        s = inv_a.state
        assert s["current_action"] == "idle"
        assert s["margin_call"] == 1
        assert s["cash"] >= 0  # 不为负
        assert s["margin_committed"] == pytest.approx(0.0)

        # Step 5: trade_history
        trades = db.execute(
            "SELECT * FROM trade_history WHERE investor_id='A' AND trigger_reason='margin_call'"
        ).fetchall()
        assert len(trades) >= 1

    def test_no_margin_call_on_small_move(
        self, inv_a: InvestorA, db: sqlite3.Connection,
    ) -> None:
        """小幅波动不触发爆仓。"""
        with db:
            inv_a.open_position(price=4700.0, margin_pct=0.8, action="cfd_long")

        assert inv_a.check_margin_call(4690.0) is False
        assert inv_a.check_margin_call(4650.0) is False


# ============================================================
# 5. 投资者 B 仓位互斥切换
# ============================================================


class TestInvestorBSwitch:
    """投资者 B：CFD → SGLN 互斥切换。"""

    def test_cfd_short_then_sgln_long(
        self, inv_b: InvestorB, db: sqlite3.Connection,
    ) -> None:
        """
        B 做 CFD 做空 → 收到 sgln_long 指令 → 先平 CFD → 再开 SGLN。
        验证全程只有 1 个仓位。
        """
        # Step 1: CFD 做空
        with db:
            inv_b.open_position(
                price=4700.0, margin_pct=0.5, action="cfd_short",
                tp=4600.0, sl=4750.0,
            )

        s = inv_b.state
        assert s["current_action"] == "cfd_short"

        # Step 2: 价格下跌 → CFD 盈利
        with db:
            inv_b.update_pnl(4680.0)

        total_after_pnl = inv_b.state["total_assets"]

        # Step 3: 模拟引擎的仓位切换逻辑（先平后开）
        with db:
            inv_b.close_position(4680.0, reason="switch_to_sgln")
        with db:
            inv_b.open_position(price=4680.0, margin_pct=0.4, action="sgln_long")

        # Step 4: 验证
        s = inv_b.state
        assert s["current_action"] == "sgln_long"
        assert s["entry_price"] == pytest.approx(4680.0)
        # margin_committed = 40% × total_assets（平仓后含盈利）
        expected_margin = total_after_pnl * 0.4
        assert s["margin_committed"] == pytest.approx(expected_margin, rel=0.01)

        # Step 5: trade_history 有 3 条（CFD开仓 + CFD平仓 + SGLN开仓）
        trades = db.execute(
            "SELECT action FROM trade_history WHERE investor_id='B' ORDER BY id"
        ).fetchall()
        actions = [t["action"] for t in trades]
        assert "cfd_short" in actions
        assert "sgln_long" in actions

    def test_sgln_then_cfd_short(
        self, inv_b: InvestorB, db: sqlite3.Connection,
    ) -> None:
        """B SGLN → 切换到 CFD 做空。"""
        with db:
            inv_b.open_position(price=4700.0, margin_pct=0.5, action="sgln_long")

        assert inv_b.state["current_action"] == "sgln_long"

        # 先平 SGLN，再开 CFD 做空
        with db:
            inv_b.close_position(4750.0, reason="switch_to_cfd")
        with db:
            inv_b.open_position(
                price=4750.0, margin_pct=0.6, action="cfd_short",
                tp=4650.0, sl=4800.0,
            )

        s = inv_b.state
        assert s["current_action"] == "cfd_short"
        assert s["entry_price"] == pytest.approx(4750.0)


# ============================================================
# 6. 决策文件校验流程
# ============================================================


class TestOrderValidationFlow:
    """模拟 OpenClaw 决策文件的读取和校验。"""

    def test_valid_orders_execute(self, inv_a: InvestorA, inv_b: InvestorB, db: sqlite3.Connection) -> None:
        """合法指令全部执行。"""
        raw = {
            "instructions": [
                {
                    "investor": "A",
                    "action": "cfd_long",
                    "margin_pct": 0.8,
                    "tp": 4800.0,
                    "sl": 4600.0,
                },
                {
                    "investor": "B",
                    "action": "idle",
                },
            ]
        }

        valid, violations = validate_orders(raw)
        assert len(valid) == 2
        assert len(violations) == 0

        # 执行 A 的指令
        inv_id, inst = valid[0]
        assert inv_id == "A"
        assert inst.action == "cfd_long"

        with db:
            inv_a.open_position(
                price=4700.0,
                margin_pct=inst.margin_pct,
                action=inst.action,
                tp=inst.tp,
                sl=inst.sl,
            )
        assert inv_a.state["current_action"] == "cfd_long"

    def test_invalid_action_blocked_with_violation(self, db: sqlite3.Connection) -> None:
        """非法指令被拦截 + violations 记录。"""
        raw = {
            "instructions": [
                {
                    "investor": "A",
                    "action": "sgln_long",  # A 不能做 sgln
                    "margin_pct": 0.5,
                },
            ]
        }

        valid, violations = validate_orders(raw)
        assert len(valid) == 0
        assert len(violations) == 1
        assert violations[0][0] == "A"  # investor_id
        assert violations[0][1] == "sgln_long"  # action

        # 记录到耻辱柱
        for inv_id, action, error in violations:
            record_violation(db, inv_id, action, error)
        db.commit()

        # 验证 violations 表
        rows = db.execute("SELECT * FROM violations WHERE investor_id='A'").fetchall()
        assert len(rows) == 1
        assert "sgln_long" in rows[0]["violation"]
        assert rows[0]["acknowledged"] == 0

    def test_mixed_orders_partial_execution(self, db: sqlite3.Connection) -> None:
        """混合指令：合法的执行，非法的拦截。"""
        raw = {
            "instructions": [
                {
                    "investor": "A",
                    "action": "cfd_short",
                    "margin_pct": 0.6,
                    "tp": 4600.0,
                    "sl": 4750.0,
                },
                {
                    "investor": "B",
                    "action": "cfd_long",  # B 不能做多
                    "margin_pct": 0.5,
                    "tp": 4800.0,
                    "sl": 4600.0,
                },
            ]
        }

        valid, violations = validate_orders(raw)
        assert len(valid) == 1
        assert len(violations) == 1
        assert valid[0][0] == "A"
        assert violations[0][0] == "B"

        # 执行合法的
        inv_a = InvestorA(db)
        inv_id, inst = valid[0]
        with db:
            inv_a.open_position(
                price=4700.0,
                margin_pct=inst.margin_pct,
                action=inst.action,
                tp=inst.tp,
                sl=inst.sl,
            )
        assert inv_a.state["current_action"] == "cfd_short"

        # 记录非法的
        for inv_id, action, error in violations:
            record_violation(db, inv_id, action, error)
        db.commit()

        rows = db.execute("SELECT * FROM violations").fetchall()
        assert len(rows) == 1

    def test_missing_margin_pct_rejected(self, db: sqlite3.Connection) -> None:
        """开仓指令缺少 margin_pct 被拒收。"""
        raw = {
            "instructions": [
                {
                    "investor": "A",
                    "action": "cfd_long",
                    "margin_pct": 0,  # 不提供
                    "tp": 4800.0,
                    "sl": 4600.0,
                },
            ]
        }

        valid, violations = validate_orders(raw)
        assert len(valid) == 0
        assert len(violations) == 1
        assert "margin_pct" in violations[0][2]

    def test_missing_tp_sl_rejected(self, db: sqlite3.Connection) -> None:
        """CFD 开仓缺少 tp/sl 被拒收。"""
        raw = {
            "instructions": [
                {
                    "investor": "A",
                    "action": "cfd_long",
                    "margin_pct": 0.8,
                    # tp 和 sl 缺失
                },
            ]
        }

        valid, violations = validate_orders(raw)
        assert len(valid) == 0
        assert len(violations) == 1
        assert "tp" in violations[0][2] or "sl" in violations[0][2]


# ============================================================
# 7. 状态报告生成
# ============================================================


class TestStateReportGeneration:
    """验证状态报告 JSON 生成。"""

    def test_report_structure(
        self, inv_a: InvestorA, inv_b: InvestorB, db: sqlite3.Connection,
    ) -> None:
        """报告结构完整，包含 system + investors。"""
        # 模拟 A 持仓
        with db:
            inv_a.open_position(
                price=4700.0, margin_pct=0.8, action="cfd_long",
                tp=4800.0, sl=4600.0,
            )
        with db:
            inv_a.update_pnl(4750.0)
        db.commit()

        report = build_state_report(
            db,
            system_state="IDLE",
            gold_price=4750.0,
            volatility=0.003,
            slope=0.001,
        )

        # 验证顶层结构
        assert report.type == "status_report"
        assert report.system.state == "IDLE"
        assert report.system.gold_price == pytest.approx(4750.0)
        assert report.system.volatility == pytest.approx(0.003)
        assert report.system.slope_3min == pytest.approx(0.001)

        # 验证投资者状态
        assert "A" in report.investors
        assert "B" in report.investors
        assert report.investors["A"].current_action == "cfd_long"
        assert report.investors["A"].entry_price == pytest.approx(4700.0)
        assert report.investors["A"].nominal_pnl > 0
        assert report.investors["B"].current_action == "idle"

    def test_report_with_warnings(self, db: sqlite3.Connection) -> None:
        """有 violations 时 warnings 字段包含记录。"""
        # 写入 violation
        record_violation(db, "B", "cfd_long", "Investor B cannot cfd_long")
        db.commit()

        warnings = get_unacknowledged_violations(db)
        assert len(warnings) == 1

        report = build_state_report(
            db,
            system_state="IDLE",
            gold_price=4700.0,
            volatility=0.0,
            slope=0.0,
            warnings=warnings,
        )

        assert len(report.warnings) == 1
        assert report.warnings[0].investor == "B"
        assert "cfd_long" in report.warnings[0].violation

    def test_write_and_read_state_file(
        self, inv_a: InvestorA, db: sqlite3.Connection, tmp_path: object,
    ) -> None:
        """状态文件写入磁盘后可被读取解析。"""
        import pathlib

        report = build_state_report(
            db,
            system_state="WATCH",
            gold_price=4700.0,
            volatility=0.005,
            slope=0.002,
        )

        # 写入临时目录
        output = tmp_path / "state_for_openclaw.json"
        output.write_text(report.model_dump_json(indent=2), encoding="utf-8")

        # 读回并验证
        loaded = json.loads(output.read_text(encoding="utf-8"))
        assert loaded["type"] == "status_report"
        assert loaded["system"]["state"] == "WATCH"
        assert loaded["system"]["gold_price"] == 4700.0
        assert "A" in loaded["investors"]
        assert "B" in loaded["investors"]


# ============================================================
# 8. 状态机 + 投资者 + 价格历史 联动
# ============================================================


class TestStateMachineIntegration:
    """状态机与投资者、价格历史联动。"""

    def test_idle_to_watch_to_trigger(self, sm: StateMachine, db: sqlite3.Connection) -> None:
        """
        注入价格序列 → 状态机 IDLE→WATCH→TRIGGER。
        """
        state = SystemState.IDLE

        # IDLE: 小斜率
        new_state = sm.transition(
            current=state, current_price=4700.0,
            total_slope=0.0001, current_slope=0.0001,
        )
        assert new_state == SystemState.IDLE

        # 斜率超过 threshold_a → WATCH
        new_state = sm.transition(
            current=state, current_price=4710.0,
            total_slope=0.002, current_slope=0.002,
        )
        assert new_state == SystemState.WATCH
        state = new_state

        # WATCH 期间斜率继续涨 → TRIGGER
        new_state = sm.transition(
            current=state, current_price=4730.0,
            total_slope=0.003, current_slope=0.003,
        )
        assert new_state == SystemState.TRIGGER

    def test_idle_to_watch_back_to_idle(self, sm: StateMachine) -> None:
        """WATCH 超时未触发 → 回到 IDLE。"""
        state = SystemState.IDLE

        # 进入 WATCH
        state = sm.transition(
            current=state, current_price=4700.0,
            total_slope=0.002, current_slope=0.002,
        )
        assert state == SystemState.WATCH

        # WATCH 超时：需要 watch_duration 次 _from_watch 调用
        # 每次价格接近 watch_start_price（斜率不触发 TRIGGER）
        for _ in range(sm.watch_duration):
            state = sm.transition(
                current=state, current_price=4700.01,
                total_slope=0.0, current_slope=0.0,
            )

        assert state == SystemState.IDLE

    def test_tp_sl_triggers_state_change(
        self, sm: StateMachine, inv_a: InvestorA, db: sqlite3.Connection,
    ) -> None:
        """投资者 TP/SL 触发时，状态机在 WATCH 状态进入 TRIGGER。"""
        with db:
            inv_a.open_position(
                price=4700.0, margin_pct=0.8, action="cfd_long",
                tp=4800.0, sl=4600.0,
            )

        # 先进入 WATCH
        state = sm.transition(
            current=SystemState.IDLE, current_price=4700.0,
            total_slope=0.002, current_slope=0.002,
        )
        assert state == SystemState.WATCH

        # TP 触发
        has_tp_sl = inv_a.check_tp_sl(4800.0) is not None
        assert has_tp_sl

        new_state = sm.transition(
            current=state, current_price=4800.0,
            total_slope=0.001, current_slope=0.001,
            has_tp_sl_trigger=has_tp_sl,
        )
        assert new_state == SystemState.TRIGGER

    def test_price_history_and_volatility(self) -> None:
        """价格历史 → 波动率和斜率计算。"""
        history = PriceHistory(maxlen=100)

        # 注入价格序列（上涨趋势）
        prices = [4700.0 + i * 5 for i in range(20)]
        for p in prices:
            history.add(p, "test")

        price_list = history.get_prices()
        assert len(price_list) == 20

        vol = calc_volatility(price_list)
        slope = calc_slope(price_list, window=15)

        assert vol > 0
        assert slope > 0  # 上涨趋势


# ============================================================
# 9. 幻觉检测
# ============================================================


class TestHallucinationDetection:
    """交易前后数值突变检测。"""

    def test_normal_trade_no_hallucination(self) -> None:
        """正常交易不触发幻觉。"""
        assert check_hallucination(10000.0, 10500.0) is False  # +5%
        assert check_hallucination(10000.0, 9500.0) is False  # -5%

    def test_hallucination_detected(self) -> None:
        """total_assets 变化 >50% → 幻觉。"""
        assert check_hallucination(10000.0, 16000.0) is True  # +60%
        assert check_hallucination(10000.0, 4000.0) is True  # -60%

    def test_zero_assets_no_crash(self) -> None:
        """total_assets=0 时不崩溃。"""
        assert check_hallucination(0.0, 5000.0) is False

    def test_hallucination_in_order_flow(
        self, inv_a: InvestorA, db: sqlite3.Connection,
    ) -> None:
        """模拟引擎的幻觉检测流程：检测到幻觉 → 记录 violation。"""
        with db:
            inv_a.open_position(
                price=4700.0, margin_pct=0.8, action="cfd_long",
                tp=4800.0, sl=4600.0,
            )

        total_before = inv_a.state["total_assets"]

        # 模拟一个合理的交易（不会触发幻觉）
        with db:
            inv_a.update_pnl(4720.0)

        total_after = inv_a.state["total_assets"]
        assert check_hallucination(total_before, total_after) is False

        # 记录到 violations 模拟幻觉被检测（虽然这次没触发）
        # 验证 violations 表可用
        record_violation(db, "A", "cfd_long", "Hallucination: assets changed >50%")
        db.commit()

        rows = db.execute("SELECT * FROM violations").fetchall()
        assert len(rows) == 1
        assert "Hallucination" in rows[0]["violation"]


# ============================================================
# 10. 端到端多 tick 模拟
# ============================================================


class TestMultiTickSimulation:
    """模拟多个 tick 的完整流程。"""

    def test_three_tick_lifecycle(
        self, inv_a: InvestorA, inv_b: InvestorB,
        sm: StateMachine, db: sqlite3.Connection,
    ) -> None:
        """
        Tick 1: 两个投资者空仓，状态 IDLE
        Tick 2: OpenClaw 发指令 → A 做多，B 做空
        Tick 3: 金价上涨 → A 盈利，B 亏损
        Tick 4: 金价继续涨 → A 触及 TP → 自动平仓
        """
        history = PriceHistory(maxlen=100)
        system_state = SystemState.IDLE

        # --- Tick 1: 空仓 ---
        price_1 = 4700.0
        history.add(price_1, "test")
        with db:
            inv_a.update_pnl(price_1)
            inv_b.update_pnl(price_1)

        assert inv_a.state["current_action"] == "idle"
        assert inv_b.state["current_action"] == "idle"
        assert system_state == SystemState.IDLE

        # --- Tick 2: OpenClaw 指令 → 开仓 ---
        raw_orders = {
            "instructions": [
                {"investor": "A", "action": "cfd_long", "margin_pct": 0.8, "tp": 4800.0, "sl": 4600.0},
                {"investor": "B", "action": "cfd_short", "margin_pct": 0.5, "tp": 4600.0, "sl": 4750.0},
            ]
        }
        valid, violations = validate_orders(raw_orders)
        assert len(valid) == 2
        assert len(violations) == 0

        price_2 = 4710.0
        investors = {"A": inv_a, "B": inv_b}
        with db:
            for inv_id, inst in valid:
                inv = investors[inv_id]
                inv.open_position(
                    price=price_2,
                    margin_pct=inst.margin_pct,
                    tp=inst.tp,
                    sl=inst.sl,
                    action=inst.action,
                )

        assert inv_a.state["current_action"] == "cfd_long"
        assert inv_b.state["current_action"] == "cfd_short"

        # --- Tick 3: 金价上涨 → A 盈利 B 亏损 ---
        price_3 = 4760.0
        history.add(price_3, "test")
        with db:
            inv_a.update_pnl(price_3)
            inv_b.update_pnl(price_3)

        assert inv_a.state["nominal_pnl"] > 0  # 做多盈利
        assert inv_b.state["nominal_pnl"] < 0  # 做空亏损

        # --- Tick 4: 金价触及 A 的 TP → 自动平仓 ---
        price_4 = 4800.0
        trigger_a = inv_a.check_tp_sl(price_4)
        assert trigger_a == "take_profit"

        with db:
            inv_a.close_position(price_4, reason="take_profit")
            inv_b.update_pnl(price_4)  # B 仍在持仓

        # 验证最终状态
        assert inv_a.state["current_action"] == "idle"
        assert inv_a.state["cash"] > 10000.0  # A 盈利
        assert inv_b.state["current_action"] == "cfd_short"  # B 仍在

        # 验证 trade_history
        trades = db.execute(
            "SELECT investor_id, action, trigger_reason FROM trade_history ORDER BY id"
        ).fetchall()
        actions_by_investor = {}
        for t in trades:
            inv_id = t["investor_id"]
            actions_by_investor.setdefault(inv_id, []).append(t["action"])

        assert "cfd_long" in actions_by_investor.get("A", [])
        assert "close" in actions_by_investor.get("A", [])
        assert "cfd_short" in actions_by_investor.get("B", [])

        # 验证状态报告可生成
        report = build_state_report(
            db, system_state="IDLE", gold_price=price_4,
            volatility=0.01, slope=0.003,
        )
        assert report.investors["A"].current_action == "idle"
        assert report.investors["B"].current_action == "cfd_short"

    def test_invalid_orders_dont_break_system(
        self, inv_a: InvestorA, inv_b: InvestorB, db: sqlite3.Connection,
    ) -> None:
        """连续收到非法指令，系统不崩溃，数据库无损。"""
        # 先让 A 开仓
        with db:
            inv_a.open_position(
                price=4700.0, margin_pct=0.8, action="cfd_long",
                tp=4800.0, sl=4600.0,
            )

        # 连续 3 轮非法指令
        bad_orders = [
            {"instructions": [{"investor": "A", "action": "sgln_long", "margin_pct": 0.5}]},
            {"instructions": [{"investor": "B", "action": "cfd_long", "margin_pct": 0.5, "tp": 4800, "sl": 4600}]},
            {"instructions": [{"investor": "A", "action": "cfd_long", "margin_pct": 0}]},
        ]

        for raw in bad_orders:
            valid, violations = validate_orders(raw)
            assert len(valid) == 0
            for inv_id, action, error in violations:
                record_violation(db, inv_id, action, error)
            db.commit()

        # A 的仓位毫发无损
        assert inv_a.state["current_action"] == "cfd_long"
        assert inv_a.state["entry_price"] == pytest.approx(4700.0)

        # violations 有 3 条记录
        rows = db.execute("SELECT * FROM violations").fetchall()
        assert len(rows) == 3

        # 状态报告包含 warnings
        warnings = get_unacknowledged_violations(db)
        assert len(warnings) == 3
