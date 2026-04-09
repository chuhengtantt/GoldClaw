"""
GoldClaw 投资者 B — SGLN 防御性狙击手。

工具: CFD 做空或 SGLN 做多（二选一，互斥）
杠杆: CFD 20x，SGLN 无杠杆
CFD 费率: Spread 1%, 隔夜 0.82%, FX 0.5%
SGLN: 无交易成本
"""

import logging
import sqlite3

from internal.exception.errors import InvalidActionError
from internal.investor.base import BaseInvestor
from internal.investor.pnl import (
    calc_cfd_pnl,
    calc_sgln_pnl,
    calc_total_assets_cfd,
    calc_total_assets_sgln,
    calc_total_assets_idle,
    is_margin_call,
)

logger = logging.getLogger(__name__)


class InvestorB(BaseInvestor):
    """投资者 B: CFD 做空 或 SGLN 做多，互斥。"""

    ALLOWED_ACTIONS = {"cfd_short", "sgln_long", "hold", "idle", "close"}
    CFD_LEVERAGE = 20.0
    SPREAD_PCT = 0.01
    OVERNIGHT_PCT = 0.0082
    FX_PCT = 0.005

    def __init__(self, conn: sqlite3.Connection) -> None:
        super().__init__(investor_id="B", conn=conn)

    def open_position(
        self,
        price: float,
        margin_pct: float = 0.0,
        tp: float = 0,
        sl: float = 0,
        **kwargs: object,
    ) -> None:
        """
        开仓：CFD 做空或 SGLN 做多。

        CFD: margin = total_assets × margin_pct, 扣 spread
        SGLN: investment = total_assets × margin_pct, 无费用
        已有仓位时先平仓再开新仓（互斥）。
        """
        action = kwargs.get("action", "cfd_short")
        if action not in self.ALLOWED_ACTIONS:
            raise InvalidActionError(f"Investor B cannot {action}")

        if action not in ("cfd_short", "sgln_long"):
            return

        s = self.state

        # 已有仓位 → 先平仓（互斥）
        if s["current_action"] not in ("idle", "hold"):
            logger.info(
                "Investor B: closing existing %s before opening %s",
                s["current_action"], action,
            )
            self.close_position(price, reason="switch")

        # 重新读取状态（平仓后 cash 已变化）
        s = self.state

        if action == "cfd_short":
            self._open_cfd_short(price, margin_pct, tp, sl, s)
        else:
            self._open_sgln_long(price, margin_pct, s)

    def _open_cfd_short(
        self, price: float, margin_pct: float, tp: float, sl: float, s: sqlite3.Row
    ) -> None:
        """CFD 做空开仓。"""
        total_assets = s["cash"] if s["current_action"] == "idle" else s["total_assets"]
        margin = total_assets * margin_pct

        if s["cash"] < margin:
            logger.warning("Insufficient margin: cash=%.2f, required=%.2f", s["cash"], margin)
            return

        pnl_result = calc_cfd_pnl(
            margin=margin, entry_price=price, current_price=price, nights_held=0,
            direction="short", leverage=self.CFD_LEVERAGE,
            spread_pct=self.SPREAD_PCT, overnight_pct=self.OVERNIGHT_PCT, fx_pct=self.FX_PCT,
        )

        actual_margin = pnl_result["actual_margin"]
        new_cash = s["cash"] - margin
        total = calc_total_assets_cfd(new_cash, actual_margin, 0.0)

        self._repo.update(
            self.investor_id,
            cash=round(new_cash, 2),
            margin_committed=round(actual_margin, 2),
            current_action="cfd_short",
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
            self.investor_id, "cfd_short", price,
            entry_price=price, margin_committed=actual_margin,
            cash_after=round(new_cash, 2), total_assets_after=round(total, 2),
        )
        logger.info("Investor B opened cfd_short: margin=%.2f, entry=%.2f", actual_margin, price)

    def _open_sgln_long(
        self, price: float, margin_pct: float, s: sqlite3.Row
    ) -> None:
        """SGLN 做多开仓（无费用）。"""
        total_assets = s["cash"] if s["current_action"] == "idle" else s["total_assets"]
        investment = total_assets * margin_pct

        if s["cash"] < investment:
            logger.warning("Insufficient cash: cash=%.2f, required=%.2f", s["cash"], investment)
            return

        new_cash = s["cash"] - investment
        total = calc_total_assets_sgln(new_cash, investment, 0.0)

        self._repo.update(
            self.investor_id,
            cash=round(new_cash, 2),
            margin_committed=round(investment, 2),
            current_action="sgln_long",
            entry_price=price,
            current_price=price,
            tp=0,
            sl=0,
            nominal_pnl=0.0,
            net_pnl=0.0,
            overnight_interest_accrued=0.0,
            nights_held=0,
            margin_call=0,
            pnl_pct=0.0,
            total_assets=round(total, 2),
        )
        self._repo.record_trade(
            self.investor_id, "sgln_long", price,
            entry_price=price, margin_committed=investment,
            cash_after=round(new_cash, 2), total_assets_after=round(total, 2),
        )
        logger.info("Investor B opened sgln_long: investment=%.2f, entry=%.2f", investment, price)

    def close_position(self, price: float, reason: str = "") -> dict[str, float]:
        """平仓。CFD 和 SGLN 各自逻辑。"""
        s = self.state
        if s["current_action"] in ("idle", "hold"):
            return {}

        if s["current_action"] == "sgln_long":
            return self._close_sgln(price, reason, s)
        else:
            return self._close_cfd(price, reason, s)

    def _close_cfd(self, price: float, reason: str, s: sqlite3.Row) -> dict[str, float]:
        """CFD 做空平仓。"""
        margin = s["margin_committed"] + s["margin_committed"] * self.SPREAD_PCT / (1 - self.SPREAD_PCT)
        pnl_result = calc_cfd_pnl(
            margin=margin, entry_price=s["entry_price"], current_price=price,
            nights_held=s["nights_held"], direction="short", leverage=self.CFD_LEVERAGE,
            spread_pct=self.SPREAD_PCT, overnight_pct=self.OVERNIGHT_PCT, fx_pct=self.FX_PCT,
        )

        nominal_pnl = pnl_result["nominal_pnl"]
        net_pnl = pnl_result["net_pnl"]
        fx_fee = pnl_result["fx_fee"]
        overnight_interest = pnl_result["overnight_interest"]

        margin_call = 0
        if is_margin_call(s["margin_committed"], nominal_pnl):
            net_pnl = -s["margin_committed"]
            margin_call = 1
            new_cash = max(0, s["cash"] + net_pnl)
            logger.critical("MARGIN CALL: Investor B CFD, loss=%.2f", abs(net_pnl))
        else:
            new_cash = s["cash"] + s["margin_committed"] + net_pnl

        total = calc_total_assets_idle(new_cash)
        fees_total = fx_fee + overnight_interest

        self._repo.update(
            self.investor_id,
            cash=round(new_cash, 2), margin_committed=0.0, current_action="idle",
            entry_price=None, current_price=price, tp=0, sl=0,
            nominal_pnl=0.0, net_pnl=0.0, overnight_interest_accrued=0.0,
            nights_held=0, margin_call=margin_call, pnl_pct=0.0, total_assets=round(total, 2),
        )
        self._repo.record_trade(
            self.investor_id, "close", price,
            entry_price=s["entry_price"], exit_price=price,
            margin_committed=s["margin_committed"],
            nominal_pnl=round(nominal_pnl, 2), net_pnl=round(net_pnl, 2),
            fees_total=round(fees_total, 2),
            cash_after=round(new_cash, 2), total_assets_after=round(total, 2),
            trigger_reason=reason,
        )
        logger.info("Investor B closed CFD: nominal=%.2f, net=%.2f, cash=%.2f", nominal_pnl, net_pnl, new_cash)
        return pnl_result

    def _close_sgln(self, price: float, reason: str, s: sqlite3.Row) -> dict[str, float]:
        """SGLN 平仓（无费用）。"""
        investment = s["margin_committed"]
        sgln_pnl = calc_sgln_pnl(investment, s["entry_price"], price)
        new_cash = s["cash"] + investment + sgln_pnl
        total = calc_total_assets_idle(new_cash)

        self._repo.update(
            self.investor_id,
            cash=round(new_cash, 2), margin_committed=0.0, current_action="idle",
            entry_price=None, current_price=price, tp=0, sl=0,
            nominal_pnl=0.0, net_pnl=0.0, overnight_interest_accrued=0.0,
            nights_held=0, margin_call=0, pnl_pct=0.0, total_assets=round(total, 2),
        )
        self._repo.record_trade(
            self.investor_id, "close", price,
            entry_price=s["entry_price"], exit_price=price,
            margin_committed=investment,
            nominal_pnl=round(sgln_pnl, 2), net_pnl=round(sgln_pnl, 2),
            fees_total=0.0,
            cash_after=round(new_cash, 2), total_assets_after=round(total, 2),
            trigger_reason=reason,
        )
        logger.info("Investor B closed SGLN: pnl=%.2f, cash=%.2f", sgln_pnl, new_cash)
        return {"nominal_pnl": sgln_pnl, "net_pnl": sgln_pnl, "sgln_pnl": sgln_pnl}

    def calc_pnl(self, current_price: float) -> dict[str, float]:
        """计算当前持仓盈亏。"""
        s = self.state
        if s["current_action"] in ("idle", "hold"):
            return {"nominal_pnl": 0.0, "net_pnl": 0.0}

        if s["current_action"] == "sgln_long":
            sgln_pnl = calc_sgln_pnl(s["margin_committed"], s["entry_price"], current_price)
            return {"nominal_pnl": sgln_pnl, "net_pnl": sgln_pnl, "sgln_pnl": sgln_pnl}

        # CFD short
        margin = s["margin_committed"] + s["margin_committed"] * self.SPREAD_PCT / (1 - self.SPREAD_PCT)
        return calc_cfd_pnl(
            margin=margin, entry_price=s["entry_price"], current_price=current_price,
            nights_held=s["nights_held"], direction="short", leverage=self.CFD_LEVERAGE,
            spread_pct=self.SPREAD_PCT, overnight_pct=self.OVERNIGHT_PCT, fx_pct=self.FX_PCT,
        )
