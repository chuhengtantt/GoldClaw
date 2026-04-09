"""
GoldClaw SQLite 连接管理 — WAL 模式。
"""

import sqlite3
import logging

from config.settings import settings

logger = logging.getLogger(__name__)


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """获取 SQLite 连接。WAL 模式，启用外键约束，允许多线程访问。"""
    path = db_path or str(settings.db_full_path)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    logger.debug("DB connection opened: %s", path)
    return conn
