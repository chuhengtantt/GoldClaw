"""
GoldClaw 主引擎 — tick 循环编排。

每个 tick 的执行顺序：
1. 获取金价
2. 记录价格历史 + 计算波动率/斜率
3. 更新状态机
4. 更新投资者盈亏
5. 检查止损/止盈/爆仓 → 自动平仓
6. 读取 OpenClaw 决策文件 → 校验 → 执行
7. 写信箱文件
8. 门铃通知（TRIGGER 时）
9. 更新 system_state 表
"""

import logging
import sqlite3
from datetime import datetime, timezone

from config.settings import settings
from internal.db.connection import get_connection
from internal.db.migrations import run_migrations, seed_initial_data
from internal.db.repository import InvestorRepository, DashboardRepository
from internal.exception.errors import GoldClawError, PriceFetchError
from internal.exception.handler import handle_tick_error
from internal.exchange.schema import EmergencyPayload
from internal.exchange.validator import (
    validate_orders,
    record_violation,
    check_hallucination,
    get_unacknowledged_violations,
)
from internal.exchange.webhook_client import (
    build_state_report,
    write_state_file,
    read_orders_file,
    ring_doorbell,
)
from internal.investor.investor_a import InvestorA
from internal.investor.investor_b import InvestorB
from internal.price.fetcher import fetch_gold_price
from internal.price.history import PriceHistory
from internal.price.volatility import calc_slope, calc_volatility
from internal.state_machine.machine import StateMachine
from internal.state_machine.states import SystemState

logger = logging.getLogger(__name__)


class Engine:
    """GoldClaw 主引擎。"""

    def __init__(self) -> None:
        self._conn: sqlite3.Connection | None = None
        self._history = PriceHistory(maxlen=1000)
        self._trigger_slope = settings.trigger_slope
        self._state_machine = StateMachine(
            threshold_a=settings.threshold_a,
            threshold_b=settings.threshold_b,
            watch_duration=settings.watch_duration,
            trigger_slope=self._trigger_slope,
            silence_period=settings.silence_period,
        )
        self._system_state = SystemState.IDLE
        self._volatility = 0.0
        self._slope = 0.0
        self._scheduler: "GoldClawScheduler | None" = None  # noqa: F821

    def initialize(self) -> None:
        """初始化：创建目录、数据库、表。"""
        # 确保 data/ 目录存在
        settings.db_full_path.parent.mkdir(parents=True, exist_ok=True)

        # 连接数据库
        self._conn = get_connection()
        run_migrations(self._conn)
        seed_initial_data(
            self._conn,
            {"A": settings.initial_cash_a, "B": settings.initial_cash_b},
        )
        self._conn.commit()
        logger.info(
            "GoldClaw initialized: DB=%s", settings.db_path,
        )

    def run_tick(self) -> None:
        """执行一次 tick。"""
        if not self._conn:
            logger.error("Engine not initialized")
            return

        try:
            self._tick_inner()
        except Exception as e:
            handle_tick_error(e)
            if self._conn:
                try:
                    self._conn.rollback()
                except Exception:
                    pass

    def _tick_inner(self) -> None:
        """tick 内部逻辑。"""
        assert self._conn is not None
        conn = self._conn
        now = datetime.now(timezone.utc).isoformat()

        # 0. 同步运行时配置
        self._sync_runtime_config(conn)

        # 1. 获取金价
        try:
            price, source = fetch_gold_price()
        except PriceFetchError:
            logger.warning("No price data, skipping tick")
            return

        logger.info("[tick] XAU $%.2f, state=%s", price, self._system_state.value)

        # 2. 记录价格历史
        self._history.add(price, source)

        # 3. 计算波动率/斜率
        prices = self._history.get_prices()
        self._volatility = calc_volatility(prices)
        self._slope = calc_slope(prices, window=settings.cycle_x)

        # 3.5 持久化价格 tick
        conn.execute(
            "INSERT INTO price_ticks (price, source, tick_time, volatility, slope) "
            "VALUES (?, ?, ?, ?, ?)",
            (price, source, now, self._volatility, self._slope),
        )

        # 3.6 记录 tick 通讯日志
        conn.execute(
            "INSERT INTO comm_log (direction, event_type, payload, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("internal", "tick", f'{{"price": {price}, "state": "{self._system_state.value}"}}', now),
        )

        # 4. 更新状态机
        self._update_state_machine(price, conn)

        # 5. 更新投资者盈亏
        investors = self._get_investors(conn)
        for inv in investors:
            inv.update_pnl(price)

        # 6. 检查止损/止盈/爆仓
        for inv in investors:
            self._check_emergencies(inv, price, conn)

        # 7. 读取并执行 OpenClaw 决策
        self._process_orders(conn)

        # 8. 写信箱
        warnings = get_unacknowledged_violations(conn)
        report = build_state_report(
            conn,
            system_state=self._system_state.value,
            gold_price=price,
            volatility=self._volatility,
            slope=self._slope,
            warnings=warnings,
        )
        write_state_file(report)

        # 8.5 记录状态报告通讯日志
        conn.execute(
            "INSERT INTO comm_log (direction, event_type, payload, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("goldclaw→openclaw", "status_report",
             f'{{"state": "{self._system_state.value}", "price": {price}}}', now),
        )

        # 9. 更新 system_state 表
        repo = InvestorRepository(conn)
        conn.execute(
            "UPDATE system_state SET state=?, gold_price=?, volatility=?, slope_3min=?, "
            "last_tick=? WHERE id=1",
            (self._system_state.value, price, self._volatility, self._slope, now),
        )
        conn.commit()

    def _sync_runtime_config(self, conn: sqlite3.Connection) -> None:
        """从 runtime_config 表读取用户修改的参数并应用。"""
        repo = DashboardRepository(conn)

        # 触发斜率
        val = repo.get_config("trigger_slope")
        if val is not None:
            try:
                new_slope = float(val)
                if new_slope != self._trigger_slope:
                    self._trigger_slope = new_slope
                    self._state_machine._trigger_slope = new_slope
                    logger.info("Runtime config: trigger_slope=%.4f", new_slope)
            except ValueError:
                pass

        # 调度间隔
        idle_val = repo.get_config("schedule_interval_idle")
        watch_val = repo.get_config("schedule_interval_watch")
        if idle_val and watch_val and self._scheduler:
            try:
                idle_min = int(idle_val)
                watch_min = int(watch_val)
                self._scheduler.update_intervals(idle_min, watch_min)
            except ValueError:
                pass

    def set_scheduler(self, scheduler: "GoldClawScheduler") -> None:  # noqa: F821
        """注入调度器引用（run.py 启动时调用）。"""
        self._scheduler = scheduler

    def _update_state_machine(self, price: float, conn: sqlite3.Connection) -> None:
        """更新状态机。"""
        investors = self._get_investors(conn)
        has_tp_sl = any(inv.check_tp_sl(price) is not None for inv in investors)
        has_margin_call = any(inv.check_margin_call(price) for inv in investors)

        new_state = self._state_machine.transition(
            current=self._system_state,
            current_price=price,
            total_slope=self._slope,
            current_slope=self._slope,
            has_tp_sl_trigger=has_tp_sl,
            has_margin_call=has_margin_call,
        )

        if new_state != self._system_state:
            logger.info("State: %s → %s", self._system_state.value, new_state.value)
            old_state = self._system_state.value
            self._system_state = new_state

            # 记录状态变化到通讯日志
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO comm_log (direction, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                ("goldclaw→openclaw", "state_change",
                 f'{{"from": "{old_state}", "to": "{new_state.value}", "price": {price}}}',
                 now),
            )

            # TRIGGER 时按门铃
            if new_state == SystemState.TRIGGER:
                self._ring_doorbell_trigger(price, conn)

    def _check_emergencies(
        self, investor: InvestorA | InvestorB, price: float, conn: sqlite3.Connection,
    ) -> None:
        """检查并处理止损/止盈/爆仓。"""
        # 先检查爆仓（优先级最高）
        if investor.check_margin_call(price):
            logger.critical("MARGIN CALL: %s at $%.2f", investor.investor_id, price)
            with conn:
                investor.close_position(price, reason="margin_call")
            self._notify_emergency("margin_call", investor.investor_id, price)
            return

        # 检查止盈/止损
        trigger = investor.check_tp_sl(price)
        if trigger:
            logger.warning("%s: %s at $%.2f", trigger, investor.investor_id, price)
            with conn:
                investor.close_position(price, reason=trigger)
            self._notify_emergency(trigger, investor.investor_id, price)

    def _process_orders(self, conn: sqlite3.Connection) -> None:
        """读取并执行 OpenClaw 决策文件。"""
        orders = read_orders_file()
        if orders is None:
            return

        logger.info("Processing orders from OpenClaw: %d instructions", len(orders.instructions))

        # 记录 OpenClaw 指令到通讯日志
        now = datetime.now(timezone.utc).isoformat()
        for inst in orders.instructions:
            conn.execute(
                "INSERT INTO comm_log (direction, event_type, payload, created_at) "
                "VALUES (?, ?, ?, ?)",
                ("openclaw→goldclaw", "order",
                 f'{{"investor": "{inst.investor}", "action": "{inst.action}"}}', now),
            )
        raw = {"instructions": [inst.model_dump() for inst in orders.instructions]}
        valid, violations = validate_orders(raw)

        # 记录违规
        for inv_id, action, error in violations:
            record_violation(conn, inv_id, action, error)

        # 执行合法指令
        investors = self._get_investors(conn)
        inv_map = {inv.investor_id: inv for inv in investors}

        for inv_id, instruction in valid:
            inv = inv_map.get(inv_id)
            if not inv:
                continue

            # 记录交易前快照（幻觉检测）
            snapshot_before = inv.state
            total_before = snapshot_before["total_assets"]

            action = instruction.action
            if action == "close":
                with conn:
                    inv.close_position(
                        snapshot_before["current_price"],
                        reason="openclaw_instruction",
                    )
            elif action in ("cfd_long", "cfd_short", "sgln_long"):
                current_price = snapshot_before["current_price"]
                if current_price <= 0:
                    current_price = self._history.latest_price or 3000.0
                with conn:
                    inv.open_position(
                        price=current_price,
                        margin_pct=instruction.margin_pct,
                        tp=instruction.tp,
                        sl=instruction.sl,
                        action=action,
                    )

                # 幻觉检测
                snapshot_after = inv.state
                if check_hallucination(total_before, snapshot_after["total_assets"]):
                    logger.critical(
                        "Hallucination detected: %s total %.2f → %.2f",
                        inv_id, total_before, snapshot_after["total_assets"],
                    )
                    record_violation(conn, inv_id, action, "Hallucination: assets changed >50%")
                    # ROLLBACK by restoring (the with conn already committed, so we update back)
                    with conn:
                        inv.update_pnl(snapshot_before["current_price"])
            # hold / idle: 不需要操作

        conn.commit()

    def _notify_emergency(
        self, event: str, investor_id: str, price: float,
    ) -> None:
        """发送紧急通知（门铃）。"""
        payload = EmergencyPayload(
            event=event,
            investor=investor_id,
            gold_price=price,
            action_taken="auto_close_position" if event != "state_trigger" else "notifying_openclaw",
            message=f"{event}: investor {investor_id} at ${price:.2f}",
        )
        ring_doorbell(payload)

    def _ring_doorbell_trigger(self, price: float, conn: sqlite3.Connection) -> None:
        """TRIGGER 时按门铃。"""
        payload = EmergencyPayload(
            event="state_trigger",
            gold_price=price,
            action_taken="notifying_openclaw",
            message=f"TRIGGER: slope exceeded threshold, gold price ${price:.2f}",
        )
        ring_doorbell(payload)

    def _get_investors(self, conn: sqlite3.Connection) -> list[InvestorA | InvestorB]:
        """获取所有投资者实例。"""
        return [InvestorA(conn), InvestorB(conn)]

    @property
    def system_state(self) -> SystemState:
        return self._system_state

    @property
    def state_machine(self) -> StateMachine:
        return self._state_machine

    def shutdown(self) -> None:
        """优雅关闭。"""
        if self._conn:
            try:
                self._conn.commit()
                self._conn.close()
                logger.info("GoldClaw stopped gracefully")
            except Exception as e:
                logger.error("Error during shutdown: %s", e)
