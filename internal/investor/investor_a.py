"""
GoldClaw 投资者 A — CFD 1:20 趋势收割者。

工具: CFD 做多或做空
杠杆: 20x
仓位: 同一时间最多 1 个 CFD 仓位
费率: Spread 1%, 隔夜 0.82%, FX 0.5%
"""

import logging
import sqlite3

from internal.exception.errors import InvalidActionError
from internal.investor.base import BaseInvestor
from internal.investor.pnl import (
    calc_cfd_pnl,
    calc_total_assets_cfd,
    calc_total_assets_idle,
    is_margin_call,
)

logger = logging.getLogger(__name__)


class InvestorA(BaseInvestor):
    """投资者 A: CFD 1:20 趋势收割者。"""

    ALLOWED_ACTIONS = {"cfd_long", "cfd_short", "hold", "idle", "close"}
    LEVERAGE = 20.0
    SPREAD_PCT = 0.01
    OVERNIGHT_PCT = 0.0082
    FX_PCT = 0.005

    def __init__(self, conn: sqlite3.Connection) -> None:
        super().__init__(investor_id="A", conn=conn)

    def open_position(
        self,
        price: float,
        margin_pct: float = 0.0,
        tp: float = 0,
        sl: float = 0,
        **kwargs: object,
    ) -> None:
        """
        CFD 开仓（做多或做空）。

        步骤：
        1. margin = total_assets × margin_pct
        2. 检查 cash ≥ margin
        3. actual_margin = margin - spread
        4. 从 cash 扣除 margin
        5. 记录 entry_price, tp, sl
        """
        action = kwargs.get("action", "cfd_long")
        if action not in self.ALLOWED_ACTIONS:
            raise InvalidActionError(f"Investor A cannot {action}")

        if action not in ("cfd_long", "cfd_short"):
            return  # hold/idle/close 不需要开仓

        s = self.state

        # 已有仓位则先平仓
        if s["current_action"] not in ("idle", "hold"):
            logger.info("Investor A: closing existing %s before opening %s", s["current_action"], action)
            self.close_position(price, reason="switch")
            s = self.state  # 平仓后重新读取状态

        # 计算保证金
        total_assets = s["cash"] if s["current_action"] == "idle" else s["total_assets"]
        margin = total_assets * margin_pct

        if s["cash"] < margin:
            logger.warning(
                "Insufficient margin: cash=%.2f, required=%.2f", s["cash"], margin
            )
            return

        direction = "long" if action == "cfd_long" else "short"
        pnl_result = calc_cfd_pnl(
            margin=margin,
            entry_price=price,
            current_price=price,
            nights_held=0,
            direction=direction,
            leverage=self.LEVERAGE,
            spread_pct=self.SPREAD_PCT,
            overnight_pct=self.OVERNIGHT_PCT,
            fx_pct=self.FX_PCT,
        )

        actual_margin = pnl_result["actual_margin"]
        new_cash = s["cash"] - margin
        total = calc_total_assets_cfd(new_cash, actual_margin, 0.0)

        self._repo.update(
            self.investor_id,
            cash=round(new_cash, 2),
            margin_committed=round(actual_margin, 2),
            current_action=action,
            entry_price=price,
            current_price=price,
            tp=tp,
            sl=sl,
            nominal_pnl=0.0,
            net_pnl=0.0,
            overnight_interest_accrued=0.0,
            nights_held=0,
            margin_call=0,
            pnl_pct=0.0,
            total_assets=round(total, 2),
        )
        self._repo.record_trade(
            self.investor_id,
            action,
            price,
            entry_price=price,
            margin_committed=actual_margin,
            cash_after=round(new_cash, 2),
            total_assets_after=round(total, 2),
        )
        logger.info(
            "Investor A opened %s: margin=%.2f, actual=%.2f, entry=%.2f",
            action, margin, actual_margin, price,
        )

    def close_position(self, price: float, reason: str = "") -> dict[str, float]:
        """
        CFD 平仓。

        步骤：
        1. 计算 nominal_pnl
        2. 扣除 FX 费 + 隔夜利息
        3. net_pnl = nominal_pnl - fx - overnight
        4. cash += actual_margin + net_pnl
        5. 爆仓检查
        """
        s = self.state
        if s["current_action"] in ("idle", "hold"):
            return {}

        direction = "long" if s["current_action"] == "cfd_long" else "short"
        pnl_result = calc_cfd_pnl(
            margin=s["margin_committed"] + s["margin_committed"] * self.SPREAD_PCT / (1 - self.SPREAD_PCT),
            entry_price=s["entry_price"],
            current_price=price,
            nights_held=s["nights_held"],
            direction=direction,
            leverage=self.LEVERAGE,
            spread_pct=self.SPREAD_PCT,
            overnight_pct=self.OVERNIGHT_PCT,
            fx_pct=self.FX_PCT,
        )

        nominal_pnl = pnl_result["nominal_pnl"]
        net_pnl = pnl_result["net_pnl"]
        fx_fee = pnl_result["fx_fee"]
        overnight_interest = pnl_result["overnight_interest"]

        # 爆仓检查
        margin_call = 0
        if is_margin_call(s["margin_committed"], nominal_pnl):
            net_pnl = -s["margin_committed"]
            margin_call = 1
            new_cash = max(0, s["cash"] + net_pnl)
            logger.critical("MARGIN CALL: Investor A, loss=%.2f", abs(net_pnl))
        else:
            new_cash = s["cash"] + s["margin_committed"] + net_pnl

        total = calc_total_assets_idle(new_cash)

        self._repo.update(
            self.investor_id,
            cash=round(new_cash, 2),
            margin_committed=0.0,
            current_action="idle",
            entry_price=None,
            current_price=price,
            tp=0,
            sl=0,
            nominal_pnl=0.0,
            net_pnl=0.0,
            overnight_interest_accrued=0.0,
            nights_held=0,
            margin_call=margin_call,
            pnl_pct=0.0,
            total_assets=round(total, 2),
        )

        fees_total = fx_fee + overnight_interest
        self._repo.record_trade(
            self.investor_id,
            "close",
            price,
            entry_price=s["entry_price"],
            exit_price=price,
            margin_committed=s["margin_committed"],
            nominal_pnl=round(nominal_pnl, 2),
            net_pnl=round(net_pnl, 2),
            fees_total=round(fees_total, 2),
            cash_after=round(new_cash, 2),
            total_assets_after=round(total, 2),
            trigger_reason=reason,
        )
        logger.info(
            "Investor A closed: nominal=%.2f, net=%.2f, cash=%.2f",
            nominal_pnl, net_pnl, new_cash,
        )
        return pnl_result

    def calc_pnl(self, current_price: float) -> dict[str, float]:
        """计算当前 CFD 持仓盈亏。"""
        s = self.state
        if s["current_action"] in ("idle", "hold"):
            return {"nominal_pnl": 0.0, "net_pnl": 0.0}

        direction = "long" if s["current_action"] == "cfd_long" else "short"
        margin = s["margin_committed"] + s["margin_committed"] * self.SPREAD_PCT / (1 - self.SPREAD_PCT)
        return calc_cfd_pnl(
            margin=margin,
            entry_price=s["entry_price"],
            current_price=current_price,
            nights_held=s["nights_held"],
            direction=direction,
            leverage=self.LEVERAGE,
            spread_pct=self.SPREAD_PCT,
            overnight_pct=self.OVERNIGHT_PCT,
            fx_pct=self.FX_PCT,
        )
