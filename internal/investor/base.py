"""
GoldClaw 投资者抽象基类。

定义开仓/平仓/盈亏计算的统一接口。
子类（InvestorA, InvestorB）实现具体逻辑。
"""

import logging
import sqlite3
from abc import ABC, abstractmethod

from internal.db.repository import InvestorRepository
from internal.investor.pnl import calc_total_assets_cfd, calc_total_assets_sgln, calc_total_assets_idle

logger = logging.getLogger(__name__)


class BaseInvestor(ABC):
    """投资者抽象基类。"""

    def __init__(self, investor_id: str, conn: sqlite3.Connection) -> None:
        self.investor_id = investor_id
        self._conn = conn
        self._repo = InvestorRepository(conn)

    @property
    def state(self) -> sqlite3.Row:
        """获取当前投资者状态（从数据库实时读取）。"""
        return self._repo.get(self.investor_id)

    @abstractmethod
    def open_position(
        self, price: float, margin_pct: float, tp: float = 0, sl: float = 0, **kwargs: object
    ) -> None:
        """开仓。调用方负责事务管理。"""
        ...

    @abstractmethod
    def close_position(self, price: float, reason: str = "") -> dict[str, float]:
        """平仓。返回盈亏详情。调用方负责事务管理。"""
        ...

    @abstractmethod
    def calc_pnl(self, current_price: float) -> dict[str, float]:
        """计算当前持仓盈亏（不写数据库）。"""
        ...

    def update_pnl(self, current_price: float) -> None:
        """每 tick 更新持仓盈亏到数据库。"""
        s = self.state
        if s["current_action"] == "idle":
            # idle 状态也更新 current_price，让 Dashboard 显示最新金价
            self._repo.update(self.investor_id, current_price=current_price)
            return

        pnl = self.calc_pnl(current_price)
        nominal_pnl = pnl["nominal_pnl"]
        net_pnl = pnl.get("net_pnl", nominal_pnl)

        if s["current_action"] == "sgln_long":
            total_assets = calc_total_assets_sgln(s["cash"], s["margin_committed"], pnl["sgln_pnl"])
        else:
            total_assets = calc_total_assets_cfd(s["cash"], s["margin_committed"], nominal_pnl)

        self._repo.update(
            self.investor_id,
            current_price=current_price,
            nominal_pnl=round(nominal_pnl, 2),
            net_pnl=round(net_pnl, 2),
            total_assets=round(total_assets, 2),
            pnl_pct=round(nominal_pnl / s["margin_committed"], 4) if s["margin_committed"] > 0 else 0,
        )

    def check_tp_sl(self, current_price: float) -> str | None:
        """检查止盈/止损是否触发。返回触发的类型或 None。"""
        s = self.state
        if s["current_action"] == "idle" or s["current_action"] == "sgln_long":
            return None  # SGLN 无 TP/SL

        tp = s["tp"]
        sl = s["sl"]

        if s["current_action"] == "cfd_long":
            if tp > 0 and current_price >= tp:
                return "take_profit"
            if sl > 0 and current_price <= sl:
                return "stop_loss"
        elif s["current_action"] == "cfd_short":
            if tp > 0 and current_price <= tp:
                return "take_profit"
            if sl > 0 and current_price >= sl:
                return "stop_loss"

        return None

    def check_margin_call(self, current_price: float) -> bool:
        """检查是否爆仓。"""
        s = self.state
        if s["current_action"] == "idle" or s["current_action"] == "sgln_long":
            return False

        pnl = self.calc_pnl(current_price)
        from internal.investor.pnl import is_margin_call
        return is_margin_call(s["margin_committed"], pnl["nominal_pnl"])
