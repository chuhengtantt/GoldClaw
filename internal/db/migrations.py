"""
GoldClaw 数据库迁移 — 幂等建表。
"""

import sqlite3
from datetime import datetime, timezone


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
    """
    CREATE TABLE IF NOT EXISTS price_ticks (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        price      REAL NOT NULL,
        source     TEXT DEFAULT '',
        tick_time  TEXT NOT NULL,
        volatility REAL DEFAULT 0,
        slope      REAL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_price_ticks_time ON price_ticks(tick_time);
    """,
    """
    CREATE TABLE IF NOT EXISTS comm_log (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        direction   TEXT NOT NULL,
        event_type  TEXT NOT NULL,
        payload     TEXT DEFAULT '{}',
        created_at  TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_comm_log_time ON comm_log(created_at);
    """,
]


def run_migrations(conn: sqlite3.Connection) -> None:
    """执行所有建表 SQL。幂等——已存在的表不会报错。"""
    for sql in MIGRATIONS:
        conn.executescript(sql)


def seed_initial_data(conn: sqlite3.Connection, investors: dict[str, float]) -> None:
    """初始化投资者数据。只在数据库为空时执行。"""
    now = datetime.now(timezone.utc).isoformat()
    for inv_id, initial_cash in investors.items():
        existing = conn.execute(
            "SELECT 1 FROM investor_state WHERE investor_id = ?", (inv_id,)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO investor_state "
                "(investor_id, total_assets, cash, initial_cash, current_action, updated_at) "
                "VALUES (?, ?, ?, ?, 'idle', ?)",
                (inv_id, initial_cash, initial_cash, initial_cash, now),
            )

    existing = conn.execute("SELECT 1 FROM system_state WHERE id = 1").fetchone()
    if not existing:
        conn.execute(
            "INSERT INTO system_state (id, state, last_tick) VALUES (1, 'IDLE', ?)",
            (now,),
        )
