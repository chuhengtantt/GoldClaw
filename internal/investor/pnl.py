"""
GoldClaw 盈亏计算 — 纯函数，无副作用。

公式来源：PRD.md 第 5 节
铁律：持仓未平期间，actual_margin 必须计入总资产。
"""


def calc_cfd_pnl(
    margin: float,
    entry_price: float,
    current_price: float,
    nights_held: int,
    direction: str = "long",
    leverage: float = 20.0,
    spread_pct: float = 0.01,
    overnight_pct: float = 0.0082,
    fx_pct: float = 0.005,
) -> dict[str, float]:
    """
    计算 CFD 盈亏（做多或做空）。

    Args:
        margin: 投入保证金。
        entry_price: 开仓金价。
        current_price: 当前金价。
        nights_held: 持仓过夜天数。
        direction: "long" 做多，"short" 做空。
        leverage: 杠杆倍数，默认 20x。
        spread_pct: 点差比例，默认 1%。
        overnight_pct: 每晚隔夜利息比例，默认 0.82%。
        fx_pct: FX 转换费比例，默认 0.5%。

    Returns:
        包含 actual_margin, nominal_exposure, nominal_pnl,
        spread, overnight_interest, fx_fee, fees_total, net_pnl 的字典。
    """
    spread = margin * spread_pct
    actual_margin = margin - spread
    nominal_exposure = actual_margin * leverage

    price_change = (
        (current_price - entry_price) / entry_price
        if direction == "long"
        else (entry_price - current_price) / entry_price
    )
    nominal_pnl = nominal_exposure * price_change

    overnight_interest = margin * overnight_pct * nights_held
    fx_fee = abs(nominal_pnl) * fx_pct
    fees_total = spread + overnight_interest + fx_fee
    net_pnl = nominal_pnl - fx_fee - overnight_interest

    return {
        "actual_margin": actual_margin,
        "nominal_exposure": nominal_exposure,
        "nominal_pnl": nominal_pnl,
        "spread": spread,
        "overnight_interest": overnight_interest,
        "fx_fee": fx_fee,
        "fees_total": fees_total,
        "net_pnl": net_pnl,
    }


def calc_cfd_long_pnl(
    margin: float,
    entry_price: float,
    current_price: float,
    nights_held: int,
    leverage: float = 20.0,
    spread_pct: float = 0.01,
    overnight_pct: float = 0.0082,
    fx_pct: float = 0.005,
) -> dict[str, float]:
    """计算 CFD 做多盈亏。参数同 calc_cfd_pnl。"""
    return calc_cfd_pnl(
        margin, entry_price, current_price, nights_held,
        direction="long", leverage=leverage,
        spread_pct=spread_pct, overnight_pct=overnight_pct, fx_pct=fx_pct,
    )


def calc_cfd_short_pnl(
    margin: float,
    entry_price: float,
    current_price: float,
    nights_held: int,
    leverage: float = 20.0,
    spread_pct: float = 0.01,
    overnight_pct: float = 0.0082,
    fx_pct: float = 0.005,
) -> dict[str, float]:
    """计算 CFD 做空盈亏。参数同 calc_cfd_pnl。"""
    return calc_cfd_pnl(
        margin, entry_price, current_price, nights_held,
        direction="short", leverage=leverage,
        spread_pct=spread_pct, overnight_pct=overnight_pct, fx_pct=fx_pct,
    )


def calc_sgln_pnl(
    investment: float,
    entry_price: float,
    current_price: float,
) -> float:
    """
    计算 SGLN 做多盈亏（无杠杆、无费用）。

    公式: pnl = investment × (current_gold_price / entry_gold_price - 1)

    Args:
        investment: 投入金额。
        entry_price: 买入时金价。
        current_price: 当前金价。

    Returns:
        盈亏金额（正为赚，负为亏）。
    """
    if entry_price == 0:
        return 0.0
    return investment * (current_price / entry_price - 1)


def calc_total_assets_cfd(
    cash: float,
    actual_margin: float,
    nominal_pnl: float,
) -> float:
    """持仓期间总资产 = cash + actual_margin + nominal_pnl。"""
    return cash + actual_margin + nominal_pnl


def calc_total_assets_sgln(
    cash: float,
    investment: float,
    sgln_pnl: float,
) -> float:
    """SGLN 持仓期间总资产 = cash + investment + pnl。"""
    return cash + investment + sgln_pnl


def calc_total_assets_idle(cash: float) -> float:
    """空仓时总资产 = cash。"""
    return cash


def is_margin_call(actual_margin: float, nominal_pnl: float) -> bool:
    """判断是否爆仓：亏损吃完全部保证金。"""
    return nominal_pnl <= -actual_margin
