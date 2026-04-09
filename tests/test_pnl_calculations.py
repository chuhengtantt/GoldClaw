"""
GoldClaw 盈亏计算测试。

覆盖 PRD.md 第 5 节所有公式：
- CFD 做多盈亏（投资者 A）
- CFD 做空盈亏（投资者 A/B）
- SGLN 做多盈亏（投资者 B）
- Spread 开仓扣除
- 隔夜利息累计
- FX 转换费（平仓扣除）
- 总资产计算
- 爆仓判断
"""

import pytest
from internal.investor.pnl import (
    calc_cfd_long_pnl,
    calc_cfd_short_pnl,
    calc_cfd_pnl,
    calc_sgln_pnl,
    calc_total_assets_cfd,
    calc_total_assets_sgln,
    calc_total_assets_idle,
    is_margin_call,
)


# ============================================================
# CFD 做多
# ============================================================

class TestCfdLong:
    """CFD 做多盈亏测试。"""

    def test_long_profit_price_up(self) -> None:
        """金价上涨 → 做多盈利。"""
        # margin=8000, entry=3000, current=3020 → +1% 涨幅
        result = calc_cfd_long_pnl(margin=8000, entry_price=3000, current_price=3020, nights_held=0)
        # actual_margin = 8000 - 80 = 7920
        # nominal_exposure = 7920 × 20 = 158400
        # nominal_pnl = 158400 × 20/3000 = 1056.0
        assert result["actual_margin"] == pytest.approx(7920.0)
        assert result["nominal_exposure"] == pytest.approx(158400.0)
        assert result["nominal_pnl"] == pytest.approx(1056.0)
        assert result["net_pnl"] > 0

    def test_long_loss_price_down(self) -> None:
        """金价下跌 → 做多亏损。"""
        result = calc_cfd_long_pnl(margin=8000, entry_price=3000, current_price=2950, nights_held=0)
        assert result["nominal_pnl"] < 0
        assert result["net_pnl"] < 0

    def test_long_no_change(self) -> None:
        """金价不变 → nominal_pnl = 0，但有 spread 损失。"""
        result = calc_cfd_long_pnl(margin=8000, entry_price=3000, current_price=3000, nights_held=0)
        assert result["nominal_pnl"] == pytest.approx(0.0)
        assert result["spread"] == pytest.approx(80.0)  # 8000 × 1%
        assert result["net_pnl"] == pytest.approx(0.0)  # fx_fee = 0, overnight = 0

    def test_long_with_overnight(self) -> None:
        """持仓过夜 → 隔夜利息累计。"""
        result = calc_cfd_long_pnl(margin=8000, entry_price=3000, current_price=3020, nights_held=3)
        # overnight = 8000 × 0.0082 × 3 = 196.8
        assert result["overnight_interest"] == pytest.approx(196.8)
        assert result["net_pnl"] < result["nominal_pnl"]  # 净利 < 名义利


# ============================================================
# CFD 做空
# ============================================================

class TestCfdShort:
    """CFD 做空盈亏测试。"""

    def test_short_profit_price_down(self) -> None:
        """金价下跌 → 做空盈利。"""
        result = calc_cfd_short_pnl(margin=8000, entry_price=3000, current_price=2950, nights_held=0)
        assert result["nominal_pnl"] > 0
        assert result["net_pnl"] > 0

    def test_short_loss_price_up(self) -> None:
        """金价上涨 → 做空亏损。"""
        result = calc_cfd_short_pnl(margin=8000, entry_price=3000, current_price=3020, nights_held=0)
        assert result["nominal_pnl"] < 0
        assert result["net_pnl"] < 0

    def test_short_symmetry_with_long(self) -> None:
        """做空亏损 = 做多盈利（同参数，方向相反）。"""
        long_result = calc_cfd_long_pnl(margin=8000, entry_price=3000, current_price=3020, nights_held=0)
        short_result = calc_cfd_short_pnl(margin=8000, entry_price=3000, current_price=3020, nights_held=0)
        assert long_result["nominal_pnl"] == pytest.approx(-short_result["nominal_pnl"])


# ============================================================
# SGLN 做多
# ============================================================

class TestSgln:
    """SGLN 做多盈亏测试。"""

    def test_sgln_profit(self) -> None:
        """金价上涨 → SGLN 盈利（无费用）。"""
        pnl = calc_sgln_pnl(investment=10000, entry_price=3000, current_price=3150)
        # 3150/3000 - 1 = 0.05 → 10000 × 0.05 = 500
        assert pnl == pytest.approx(500.0)

    def test_sgln_loss(self) -> None:
        """金价下跌 → SGLN 亏损。"""
        pnl = calc_sgln_pnl(investment=10000, entry_price=3000, current_price=2850)
        # 2850/3000 - 1 = -0.05 → -500
        assert pnl == pytest.approx(-500.0)

    def test_sgln_no_change(self) -> None:
        """金价不变 → PnL = 0。"""
        pnl = calc_sgln_pnl(investment=10000, entry_price=3000, current_price=3000)
        assert pnl == pytest.approx(0.0)

    def test_sgln_zero_entry(self) -> None:
        """entry_price=0 → 返回 0（防除零）。"""
        pnl = calc_sgln_pnl(investment=10000, entry_price=0, current_price=3000)
        assert pnl == 0.0


# ============================================================
# Spread
# ============================================================

class TestSpread:
    """Spread 点差测试。"""

    def test_spread_deducted(self) -> None:
        """开仓时 spread 从 margin 中扣除。"""
        result = calc_cfd_long_pnl(margin=10000, entry_price=3000, current_price=3000, nights_held=0)
        # spread = 10000 × 1% = 100
        assert result["spread"] == pytest.approx(100.0)
        # actual_margin = 10000 - 100 = 9900
        assert result["actual_margin"] == pytest.approx(9900.0)

    def test_spread_custom_pct(self) -> None:
        """自定义 spread 比例。"""
        result = calc_cfd_long_pnl(
            margin=10000, entry_price=3000, current_price=3000,
            nights_held=0, spread_pct=0.02,
        )
        assert result["spread"] == pytest.approx(200.0)


# ============================================================
# FX 转换费
# ============================================================

class TestFx:
    """FX 转换费测试。"""

    def test_fx_on_profit(self) -> None:
        """盈利时 FX 费用 > 0。"""
        result = calc_cfd_long_pnl(margin=8000, entry_price=3000, current_price=3020, nights_held=0)
        # fx_fee = abs(nominal_pnl) × 0.5%
        assert result["fx_fee"] > 0
        assert result["fx_fee"] == pytest.approx(abs(result["nominal_pnl"]) * 0.005)

    def test_fx_on_loss(self) -> None:
        """亏损时 FX 费用仍然 > 0（取绝对值）。"""
        result = calc_cfd_long_pnl(margin=8000, entry_price=3000, current_price=2950, nights_held=0)
        assert result["fx_fee"] > 0
        assert result["fx_fee"] == pytest.approx(abs(result["nominal_pnl"]) * 0.005)


# ============================================================
# 总资产
# ============================================================

class TestTotalAssets:
    """总资产计算测试。"""

    def test_cfd_total_assets_with_profit(self) -> None:
        """CFD 持仓盈利：总资产 > 初始。"""
        result = calc_cfd_long_pnl(margin=8000, entry_price=3000, current_price=3020, nights_held=0)
        cash = 2000.0  # 剩余现金
        total = calc_total_assets_cfd(cash, result["actual_margin"], result["nominal_pnl"])
        # 2000 + 7920 + 1056 = 10976
        assert total == pytest.approx(10976.0)

    def test_sgln_total_assets(self) -> None:
        """SGLN 持仓总资产。"""
        cash = 5000.0
        investment = 5000.0
        pnl = calc_sgln_pnl(investment, entry_price=3000, current_price=3150)
        total = calc_total_assets_sgln(cash, investment, pnl)
        # 5000 + 5000 + 250 = 10250
        assert total == pytest.approx(10250.0)

    def test_idle_total_assets(self) -> None:
        """空仓：总资产 = cash。"""
        assert calc_total_assets_idle(10000.0) == 10000.0


# ============================================================
# 爆仓
# ============================================================

class TestMarginCall:
    """爆仓判断测试。"""

    def test_no_margin_call(self) -> None:
        """盈利状态不爆仓。"""
        result = calc_cfd_long_pnl(margin=8000, entry_price=3000, current_price=3020, nights_held=0)
        assert not is_margin_call(result["actual_margin"], result["nominal_pnl"])

    def test_margin_call(self) -> None:
        """亏损超过保证金 → 爆仓。"""
        # actual_margin = 7920, nominal_pnl = -8000 (< -7920)
        assert is_margin_call(actual_margin=7920.0, nominal_pnl=-8000.0)

    def test_exactly_at_margin(self) -> None:
        """亏损恰好等于保证金 → 爆仓（≤条件）。"""
        assert is_margin_call(actual_margin=7920.0, nominal_pnl=-7920.0)
