"""
GoldClaw 数据访问层 — InvestorRepository。
"""

import sqlite3
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class InvestorRepository:
    """投资者数据访问。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, investor_id: str) -> sqlite3.Row:
        """获取投资者当前状态。"""
        row = self._conn.execute(
            "SELECT * FROM investor_state WHERE investor_id = ?", (investor_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Investor {investor_id} not found")
        return row

    def update(self, investor_id: str, **kwargs: object) -> None:
        """更新投资者状态。调用方负责事务。"""
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        columns = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [investor_id]
        self._conn.execute(
            f"UPDATE investor_state SET {columns} WHERE investor_id = ?", values
        )

    def record_trade(
        self, investor_id: str, action: str, gold_price: float, **details: object
    ) -> None:
        """记录交易到 trade_history。INSERT Only。"""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO trade_history "
            "(timestamp, investor_id, action, gold_price, entry_price, exit_price, "
            "margin_committed, nominal_pnl, net_pnl, fees_total, cash_after, total_assets_after, "
            "trigger_reason, signal_strength, signal_type, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                now, investor_id, action, gold_price,
                details.get("entry_price"),
                details.get("exit_price"),
                details.get("margin_committed"),
                details.get("nominal_pnl"),
                details.get("net_pnl"),
                details.get("fees_total"),
                details.get("cash_after"),
                details.get("total_assets_after"),
                details.get("trigger_reason"),
                details.get("signal_strength"),
                details.get("signal_type"),
                details.get("reasoning"),
            ),
        )
