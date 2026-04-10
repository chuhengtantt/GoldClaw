"""
GoldClaw 数据库备份 — SQLite WAL 安全备份 + 滚动保留。
"""

import logging
import os
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


def backup_database(db_path: str | Path, backup_dir: str | Path, max_backups: int = 10) -> str:
    """
    SQLite 安全备份（WAL checkpoint + 文件复制）。

    1. PRAGMA wal_checkpoint(TRUNCATE) 确保 WAL 数据合入主库
    2. 复制 .db 文件到 backup_dir/goldclaw_YYYYMMDD_HHMMSS.db
    3. 删除超过 max_backups 的旧备份

    返回备份文件路径。
    """
    db_path = Path(db_path)
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    # Step 1: Checkpoint WAL
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
    except Exception as e:
        logger.warning("WAL checkpoint failed (non-fatal): %s", e)

    # Step 2: Copy database file
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_name = f"goldclaw_{timestamp}.db"
    backup_path = backup_dir / backup_name
    shutil.copy2(str(db_path), str(backup_path))

    logger.info("Backup created: %s (%d bytes)", backup_path, backup_path.stat().st_size)

    # Step 3: Rolling cleanup — keep only max_backups
    _cleanup_old_backups(backup_dir, max_backups)

    return str(backup_path)


def list_backups(backup_dir: str | Path) -> list[dict]:
    """列出所有备份文件，按时间倒序。"""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []

    backups = []
    for f in sorted(backup_dir.glob("goldclaw_*.db"), reverse=True):
        stat = f.stat()
        # Parse timestamp from filename: goldclaw_YYYYMMDD_HHMMSS.db
        name = f.stem  # goldclaw_20260410_203000
        ts_part = name.replace("goldclaw_", "")
        try:
            dt = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
            time_label = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            time_label = ts_part

        backups.append({
            "filename": f.name,
            "size": stat.st_size,
            "size_label": _fmt_size(stat.st_size),
            "time": time_label,
        })

    return backups


def restore_database(db_path: str | Path, backup_path: str | Path) -> None:
    """从备份恢复数据库（覆盖当前数据库）。"""
    db_path = Path(db_path)
    backup_path = Path(backup_path)

    if not backup_path.exists():
        raise FileNotFoundError(f"Backup not found: {backup_path}")

    # Remove WAL/SHM files to avoid conflicts
    for suffix in ("-wal", "-shm"):
        p = db_path.parent / (db_path.name + suffix)
        if p.exists():
            p.unlink()

    shutil.copy2(str(backup_path), str(db_path))
    logger.info("Database restored from %s", backup_path)


def _cleanup_old_backups(backup_dir: Path, max_backups: int) -> int:
    """删除超过 max_backups 的旧备份，返回删除数量。"""
    backups = sorted(backup_dir.glob("goldclaw_*.db"))
    deleted = 0
    while len(backups) > max_backups:
        oldest = backups.pop(0)
        oldest.unlink()
        deleted += 1
        logger.debug("Deleted old backup: %s", oldest.name)
    return deleted


def _fmt_size(size: int) -> str:
    """Format file size for display."""
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / 1024 / 1024:.1f} MB"
