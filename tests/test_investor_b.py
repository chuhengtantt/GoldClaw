"""
GoldClaw 投资者 B 测试。

覆盖：CFD 做空、SGLN 做多、互斥切换、SGLN 无 TP/SL、平仓盈亏。
"""

import pytest
import sqlite3

from internal.db.connection import get_connection
from internal.db.migrations import run_migrations, seed_initial_data
from internal.investor.investor_b import InvestorB
from internal.exception.errors import InvalidActionError


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = get_connection(":memory:")
    run_migrations(conn)
    seed_initial_data(conn, {"B": 10000.0})
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def investor(db: sqlite3.Connection) -> InvestorB:
    return InvestorB(db)


class TestInvestorBOpenCfd:
    """CFD 做空开仓。"""

    def test_open_cfd_short(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short")

        s = investor.state
        assert s["current_action"] == "cfd_short"
        assert s["margin_committed"] == pytest.approx(7920.0)
        assert s["cash"] == pytest.approx(2000.0)

    def test_open_cfd_with_tp_sl(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short", tp=2900, sl=3100)

        s = investor.state
        assert s["tp"] == 2900
        assert s["sl"] == 3100


class TestInvestorBOpenSgln:
    """SGLN 做多开仓。"""

    def test_open_sgln_long(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """SGLN 开仓：无 spread，investment 直接扣除。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.5, action="sgln_long")

        s = investor.state
        assert s["current_action"] == "sgln_long"
        # investment = 10000 × 0.5 = 5000, 无费用
        assert s["margin_committed"] == pytest.approx(5000.0)
        assert s["cash"] == pytest.approx(5000.0)
        # SGLN 无 TP/SL
        assert s["tp"] == 0
        assert s["sl"] == 0


class TestInvestorBReject:
    """非法操作拒绝。"""

    def test_reject_cfd_long(self, investor: InvestorB) -> None:
        """投资者 B 不能做 CFD 做多。"""
        with pytest.raises(InvalidActionError):
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_long")


class TestInvestorBExclusive:
    """CFD 和 SGLN 互斥测试。"""

    def test_cfd_to_sgln(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """CFD 空仓 → 切换到 SGLN 多仓（先平 CFD 再开 SGLN）。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short")
        assert investor.state["current_action"] == "cfd_short"

        with db:
            investor.open_position(price=2950, margin_pct=0.5, action="sgln_long")

        s = investor.state
        assert s["current_action"] == "sgln_long"
        # CFD 空仓在2950平仓是盈利的，所以 cash 应该 > 2000
        assert s["cash"] > 2000.0

    def test_sgln_to_cfd(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """SGLN 多仓 → 切换到 CFD 空仓。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.5, action="sgln_long")

        with db:
            investor.open_position(price=3020, margin_pct=0.8, action="cfd_short")

        s = investor.state
        assert s["current_action"] == "cfd_short"


class TestInvestorBClose:
    """平仓测试。"""

    def test_close_cfd_profit(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """CFD 做空盈利平仓。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short")
        with db:
            investor.close_position(price=2950)

        s = investor.state
        assert s["current_action"] == "idle"
        assert s["cash"] > 10000.0

    def test_close_cfd_loss(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """CFD 做空亏损平仓。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short")
        with db:
            investor.close_position(price=3050)

        s = investor.state
        assert s["current_action"] == "idle"
        assert s["cash"] < 10000.0

    def test_close_sgln_profit(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """SGLN 盈利平仓（金价上涨）。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.5, action="sgln_long")
        with db:
            investor.close_position(price=3150)

        s = investor.state
        assert s["current_action"] == "idle"
        # investment=5000, pnl = 5000 × (3150/3000 - 1) = 250
        # cash = 5000 + 5000 + 250 = 10250
        assert s["cash"] == pytest.approx(10250.0)

    def test_close_sgln_loss(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """SGLN 亏损平仓（金价下跌）。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.5, action="sgln_long")
        with db:
            investor.close_position(price=2850)

        s = investor.state
        # pnl = 5000 × (2850/3000 - 1) = -250
        # cash = 5000 + 5000 - 250 = 9750
        assert s["cash"] == pytest.approx(9750.0)


class TestInvestorBSglnNoTpSl:
    """SGLN 无 TP/SL。"""

    def test_sgln_no_tp_sl_trigger(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """SGLN 持仓不触发 TP/SL。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.5, action="sgln_long")

        # 即使价格大幅波动也不触发
        assert investor.check_tp_sl(5000) is None
        assert investor.check_tp_sl(1000) is None

    def test_sgln_no_margin_call(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """SGLN 无爆仓风险。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.5, action="sgln_long")

        assert investor.check_margin_call(1000) is False


class TestInvestorBPnl:
    """盈亏计算测试。"""

    def test_update_pnl_sgln(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """更新 SGLN 持仓盈亏。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.5, action="sgln_long")
        with db:
            investor.update_pnl(3150)

        s = investor.state
        # sgln_pnl = 5000 × (3150/3000 - 1) = 250
        # total = 5000 + 5000 + 250 = 10250
        assert s["nominal_pnl"] == pytest.approx(250.0)
        assert s["total_assets"] == pytest.approx(10250.0)

    def test_update_pnl_cfd(self, investor: InvestorB, db: sqlite3.Connection) -> None:
        """更新 CFD 做空盈亏。"""
        with db:
            investor.open_position(price=3000, margin_pct=0.8, action="cfd_short")
        with db:
            investor.update_pnl(2950)

        s = investor.state
        assert s["nominal_pnl"] > 0  # 做空，金价下跌，盈利
