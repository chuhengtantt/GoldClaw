"""
GoldClaw 数据库操作模式参考
AI 写数据库代码时必须照这个模式来。
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from config.settings import settings


# ============================================================
# 1. 连接管理：WAL 模式 + 单例
# ============================================================

def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """
    获取 SQLite 连接。
    WAL 模式：读写不互相阻塞。
    foreign_keys：启用外键约束。
    """
    path = db_path or settings.db_path
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row  # 返回字典式行
    return conn


# ============================================================
# 2. 建表迁移：幂等执行
# ============================================================

MIGRATIONS = [
    """
    CREATE TABLE IF NOT EXISTS investor_state (
        investor_id       TEXT PRIMARY KEY,
        total_assets      REAL NOT NULL DEFAULT 0,
        cash              REAL NOT NULL DEFAULT 0,
        margin_committed  REAL NOT NULL DEFAULT 0,
        current_action    TEXT NOT NULL DEFAULT 'idle',
        entry_price       REAL,
        current_price     REAL NOT NULL DEFAULT 0,
        tp                REAL DEFAULT 0,
        sl                REAL DEFAULT 0,
        nominal_pnl       REAL NOT NULL DEFAULT 0,
        net_pnl           REAL NOT NULL DEFAULT 0,
        overnight_interest_accrued REAL NOT NULL DEFAULT 0,
        nights_held       INTEGER NOT NULL DEFAULT 0,
        margin_call       INTEGER NOT NULL DEFAULT 0,
        pnl_pct           REAL NOT NULL DEFAULT 0,
        entry_timestamp   TEXT,
        initial_cash      REAL NOT NULL DEFAULT 10000,
        updated_at        TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trade_history (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT NOT NULL,
        investor_id     TEXT NOT NULL,
        action          TEXT NOT NULL,
        gold_price      REAL NOT NULL,
        entry_price     REAL,
        exit_price      REAL,
        margin_committed REAL,
        nominal_pnl     REAL,
        net_pnl         REAL,
        fees_total      REAL,
        cash_after      REAL NOT NULL,
        total_assets_after REAL NOT NULL,
        trigger_reason  TEXT,
        signal_strength REAL,
        signal_type     TEXT,
        reasoning       TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS system_state (
        id              INTEGER PRIMARY KEY CHECK (id = 1),
        state           TEXT NOT NULL DEFAULT 'IDLE',
        gold_price      REAL NOT NULL DEFAULT 0,
        price_source    TEXT DEFAULT '',
        volatility      REAL NOT NULL DEFAULT 0,
        slope_3min      REAL NOT NULL DEFAULT 0,
        entered_at      TEXT,
        watch_start_price REAL,
        watch_start_time TEXT,
        silence_until   TEXT,
        prev_slope      REAL DEFAULT 0,
        last_tick       TEXT NOT NULL,
        last_price_update TEXT
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS violations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp       TEXT NOT NULL,
        investor_id     TEXT NOT NULL,
        violation       TEXT NOT NULL,
        original_action TEXT NOT NULL,
        action_taken    TEXT NOT NULL,
        acknowledged    INTEGER DEFAULT 0
    );
    """,
]


def run_migrations(conn: sqlite3.Connection) -> None:
    """执行所有建表 SQL。幂等——已存在的表不会报错。"""
    for sql in MIGRATIONS:
        conn.executescript(sql)


def seed_initial_data(conn: sqlite3.Connection, investors: dict[str, float]) -> None:
    """
    初始化投资者数据。只在数据库为空时执行。
    investors: {"A": 10000.0, "B": 10000.0}
    """
    now = datetime.now(timezone.utc).isoformat()
    for inv_id, initial_cash in investors.items():
        existing = conn.execute(
            "SELECT 1 FROM investor_state WHERE investor_id = ?", (inv_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO investor_state (investor_id, total_assets, cash, initial_cash, current_action, updated_at) "
                "VALUES (?, ?, ?, ?, 'idle', ?)",
                (inv_id, initial_cash, initial_cash, initial_cash, now),
            )

    # system_state 只有一行
    existing = conn.execute("SELECT 1 FROM system_state WHERE id = 1").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO system_state (id, state, last_tick) VALUES (1, 'IDLE', ?)",
            (now,),
        )


# ============================================================
# 3. 数据访问层：Repository 模式
# ============================================================

class InvestorRepository:
    """投资者数据访问。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get(self, investor_id: str) -> sqlite3.Row:
        """获取投资者当前状态。"""
        row = self._conn.execute(
            "SELECT * FROM investor_state WHERE investor_id = ?", (investor_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Investor {investor_id} not found")
        return row

    def update(self, investor_id: str, **kwargs) -> None:
        """更新投资者状态。调用方负责事务。"""
        kwargs["updated_at"] = datetime.now(timezone.utc).isoformat()
        columns = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [investor_id]
        self._conn.execute(
            f"UPDATE investor_state SET {columns} WHERE investor_id = ?", values
        )

    def record_trade(self, investor_id: str, action: str, gold_price: float, **details) -> None:
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
                details.get("entry_price"), details.get("exit_price"),
                details.get("margin_committed"), details.get("nominal_pnl"),
                details.get("net_pnl"), details.get("fees_total"),
                details.get("cash_after"), details.get("total_assets_after"),
                details.get("trigger_reason"), details.get("signal_strength"),
                details.get("signal_type"), details.get("reasoning"),
            ),
        )


# ============================================================
# 4. 使用示例
# ============================================================

def example_usage() -> None:
    conn = get_connection()
    run_migrations(conn)
    seed_initial_data(conn, {"A": 10000.0, "B": 10000.0})
    conn.commit()

    repo = InvestorRepository(conn)

    # 事务：开仓 + 记录交易
    with conn:
        repo.update("A", cash=2000.0, margin_committed=8000.0, current_action="cfd_long", entry_price=3020.0)
        repo.record_trade("A", "cfd_long", 3020.0, entry_price=3020.0, margin_committed=8000.0)

    conn.close()
