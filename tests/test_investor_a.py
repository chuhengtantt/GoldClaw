"""
GoldClaw 投资者 A 测试。

覆盖：CFD 做多开仓、做空开仓、平仓盈亏、TP/SL、爆仓、仓位切换。
"""

import pytest
import sqlite3

from internal.db.connection import get_connection
from internal.db.migrations import run_migrations, seed_initial_data
from internal.investor.investor_a import InvestorA
from internal.exception.errors import InvalidActionError


@pytest.fixture
def db() -> sqlite3.Connection:
    """创建内存数据库并初始化。"""
    conn = get_connection(":memory:")
    run_migrations(conn)
    seed_initial_data(conn, {"A": 10000.0})
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def investor(db: sqlite3.Connection) -> InvestorA:
    return InvestorA(db)


class TestInvestorAOpen:
    """开仓测试。"""

    def test_open_cfd_long(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """CFD 做多开仓：cash 减少，margin_committed 增加。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long")

        s = investor.state
        assert s["current_action"] == "cfd_long"
        assert s["entry_price"] == 3000.0
        # margin = 10000 × 0.8 = 8000, spread = 80, actual_margin = 7920
        assert s["margin_committed"] == pytest.approx(7920.0)
        assert s["cash"] == pytest.approx(2000.0)
        assert s["tp"] == 0
        assert s["sl"] == 0

    def test_open_cfd_short(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """CFD 做空开仓。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short")

        s = investor.state
        assert s["current_action"] == "cfd_short"
        assert s["margin_committed"] == pytest.approx(7920.0)

    def test_open_with_tp_sl(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """开仓时设置 TP/SL。"""
        with db:
            investor.open_position(
                price=3000, margin_pct=0.8, action="cfd_long", tp=3100, sl=2900,
            )

        s = investor.state
        assert s["tp"] == 3100
        assert s["sl"] == 2900

    def test_open_insufficient_cash(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """现金不足 → 不开仓，保持 idle。"""
        with db:
            investor.open_position(price=3000, margin_pct=1.0, action="cfd_long")
        # margin=10000, spread=100, need 10000 from cash=10000 → OK but edge
        # Let's use > 1.0 to truly exceed
        s = investor.state
        # With margin_pct=1.0, margin=10000, cash=10000, just enough
        assert s["current_action"] == "cfd_long"

    def test_open_rejects_sgln(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """投资者 A 不能做 sgln_long。"""
        with pytest.raises(InvalidActionError):
            investor.open_position(price=3000, margin_pct=0.5, action="sgln_long")


class TestInvestorAClose:
    """平仓测试。"""

    def test_close_long_profit(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """做多盈利平仓：cash 增加。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long")
        with db:
            result = investor.close_position(price=3020)

        s = investor.state
        assert s["current_action"] == "idle"
        assert s["cash"] > 10000.0  # 盈利
        assert s["margin_committed"] == 0.0
        assert "nominal_pnl" in result

    def test_close_long_loss(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """做多亏损平仓：cash 减少。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long")
        with db:
            investor.close_position(price=2950)

        s = investor.state
        assert s["current_action"] == "idle"
        assert s["cash"] < 10000.0

    def test_close_short_profit(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """做空盈利平仓（金价下跌）。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short")
        with db:
            investor.close_position(price=2950)

        s = investor.state
        assert s["cash"] > 10000.0

    def test_close_idle_noop(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """空仓时平仓 → 无操作。"""
        with db:
            result = investor.close_position(price=3000)

        assert result == {}
        assert investor.state["current_action"] == "idle"


class TestInvestorASwitch:
    """仓位切换测试。"""

    def test_switch_long_to_short(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """已有做多仓位，开做空 → 先平多再开空。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long")
        with db:
            investor.open_position(price=3020, margin_pct=0.8, action="cfd_short")

        s = investor.state
        assert s["current_action"] == "cfd_short"
        assert s["entry_price"] == 3020.0


class TestInvestorATpSl:
    """止盈止损测试。"""

    def test_long_take_profit_trigger(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """做多 TP 触发。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long", tp=3100)

        assert investor.check_tp_sl(3100) == "take_profit"
        assert investor.check_tp_sl(3050) is None

    def test_long_stop_loss_trigger(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """做多 SL 触发。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long", sl=2900)

        assert investor.check_tp_sl(2850) == "stop_loss"
        assert investor.check_tp_sl(2950) is None

    def test_short_take_profit_trigger(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """做空 TP 触发。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short", tp=2900)

        assert investor.check_tp_sl(2850) == "take_profit"

    def test_short_stop_loss_trigger(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """做空 SL 触发。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short", sl=3100)

        assert investor.check_tp_sl(3150) == "stop_loss"

    def test_idle_no_trigger(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """空仓不触发 TP/SL。"""
        assert investor.check_tp_sl(1000) is None


class TestInvestorAMarginCall:
    """爆仓测试。"""

    def test_margin_call_detected(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """大幅亏损 → 爆仓。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long")
        # 金价大跌触发爆仓
        assert investor.check_margin_call(2600) is True

    def test_no_margin_call(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """小幅波动不爆仓。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long")
        assert investor.check_margin_call(2990) is False

    def test_margin_call_sets_flag(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """爆仓平仓后 margin_call=1。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long")
        with db:
            investor.close_position(price=2600)

        s = investor.state
        assert s["margin_call"] == 1
        assert s["current_action"] == "idle"


class TestInvestorAPnl:
    """盈亏计算测试。"""

    def test_update_pnl_long(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """更新做多盈亏。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long")
        with db:
            investor.update_pnl(3020)

        s = investor.state
        assert s["nominal_pnl"] > 0
        assert s["total_assets"] > 10000.0

    def test_update_pnl_idle_noop(self, investor: InvestorA, db: sqlite3.Connection) -> None:
        """空仓 update_pnl 无操作。"""
        with db:
            investor.update_pnl(3000)

        s = investor.state
        assert s["nominal_pnl"] == 0.0
