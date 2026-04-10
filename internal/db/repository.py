"""
GoldClaw 数据访问层 — InvestorRepository + DashboardRepository。
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
            "trigger_reason, signal_strength, signal_type, reasoning, tp, sl) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                details.get("tp", 0),
                details.get("sl", 0),
            ),
        )


class DashboardRepository:
    """Dashboard 数据访问。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_price_ticks(self, since: str | None = None, limit: int = 1000) -> list[sqlite3.Row]:
        """获取价格 tick 历史。since 为 ISO 8601 UTC 时间戳。"""
        if since:
            rows = self._conn.execute(
                "SELECT price, source, tick_time, volatility, slope "
                "FROM price_ticks WHERE tick_time >= ? ORDER BY tick_time ASC LIMIT ?",
                (since, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT price, source, tick_time, volatility, slope "
                "FROM price_ticks ORDER BY tick_time DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return rows

    def get_latest_tick(self) -> sqlite3.Row | None:
        """获取最新价格 tick。"""
        return self._conn.execute(
            "SELECT price, source, tick_time, volatility, slope "
            "FROM price_ticks ORDER BY tick_time DESC LIMIT 1"
        ).fetchone()

    def get_all_investors(self) -> list[sqlite3.Row]:
        """获取所有投资者当前状态。"""
        return self._conn.execute(
            "SELECT * FROM investor_state ORDER BY investor_id"
        ).fetchall()

    def get_trade_history(
        self, investor_id: str | None = None, page: int = 1, size: int = 20,
    ) -> tuple[list[sqlite3.Row], int]:
        """获取交易历史，返回 (rows, total_count)。"""
        offset = (page - 1) * size
        if investor_id:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM trade_history WHERE investor_id = ?",
                (investor_id,),
            ).fetchone()[0]
            rows = self._conn.execute(
                "SELECT * FROM trade_history WHERE investor_id = ? "
                "ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (investor_id, size, offset),
            ).fetchall()
        else:
            total = self._conn.execute(
                "SELECT COUNT(*) FROM trade_history"
            ).fetchone()[0]
            rows = self._conn.execute(
                "SELECT * FROM trade_history ORDER BY timestamp DESC LIMIT ? OFFSET ?",
                (size, offset),
            ).fetchall()
        return rows, total

    def get_comm_log(self, page: int = 1, size: int = 50) -> tuple[list[sqlite3.Row], int]:
        """获取通讯日志，返回 (rows, total_count)。"""
        offset = (page - 1) * size
        total = self._conn.execute("SELECT COUNT(*) FROM comm_log").fetchone()[0]
        rows = self._conn.execute(
            "SELECT * FROM comm_log ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (size, offset),
        ).fetchall()
        return rows, total

    def get_comm_daily_summary(self, since: str | None = None) -> list[dict]:
        """按天聚合通讯日志，返回每天的 GC→OC / OC→GC 成功次数。"""
        query = (
            "SELECT DATE(created_at) as day, "
            "COUNT(CASE WHEN direction IN ('goldclaw→openclaw','internal') THEN 1 END) as gc_out, "
            "COUNT(CASE WHEN direction = 'openclaw→goldclaw' THEN 1 END) as oc_in "
            "FROM comm_log"
        )
        params: list[str] = []
        if since:
            query += " WHERE created_at >= ?"
            params.append(since)
        query += " GROUP BY DATE(created_at) ORDER BY day"
        rows = self._conn.execute(query, params).fetchall()
        return [
            {"day": row["day"], "gc_out": row["gc_out"], "oc_in": row["oc_in"]}
            for row in rows
        ]

    def get_system_state(self) -> sqlite3.Row | None:
        """获取系统状态。"""
        return self._conn.execute(
            "SELECT * FROM system_state WHERE id = 1"
        ).fetchone()

    def get_table_stats(self) -> dict[str, int]:
        """获取各表行数统计。"""
        stats = {}
        for table in ("price_ticks", "comm_log", "trade_history", "violations"):
            try:
                count = self._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                stats[table] = count
            except Exception:
                stats[table] = 0
        return stats

    def delete_price_ticks_before(self, before: str) -> int:
        """删除指定时间之前的价格 tick，返回删除行数。"""
        cur = self._conn.execute(
            "DELETE FROM price_ticks WHERE tick_time < ?", (before,)
        )
        self._conn.commit()
        return cur.rowcount

    def delete_comm_log_before(self, before: str) -> int:
        """删除指定时间之前的通讯日志，返回删除行数。"""
        cur = self._conn.execute(
            "DELETE FROM comm_log WHERE created_at < ?", (before,)
        )
        self._conn.commit()
        return cur.rowcount

    def get_config(self, key: str, default: str | None = None) -> str | None:
        """读取运行时配置。"""
        row = self._conn.execute(
            "SELECT value FROM runtime_config WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def get_all_config(self) -> dict[str, str]:
        """读取所有运行时配置。"""
        rows = self._conn.execute("SELECT key, value FROM runtime_config").fetchall()
        return {row["key"]: row["value"] for row in rows}

    def set_config(self, key: str, value: str) -> None:
        """写入运行时配置（UPSERT）。"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO runtime_config (key, value, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=?, updated_at=?",
            (key, value, now, value, now),
        )
        self._conn.commit()
