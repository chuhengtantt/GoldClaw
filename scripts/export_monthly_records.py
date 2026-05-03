#!/usr/bin/env python3
"""Export GoldClaw monthly investor records to a dependency-free XLSX file."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from simple_xlsx import write_xlsx


DB_PATH = Path("/Users/orcastt/GoldClaw/data/goldclaw.db")
DATA_DIR = Path("/Users/orcastt/GoldClaw/data")
EXPORT_DIR = Path("/Users/orcastt/GoldClaw/exports")


def parse_args() -> argparse.Namespace:
    now = datetime.now(timezone.utc)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--year", type=int, default=now.year)
    parser.add_argument("--month", type=int, default=now.month)
    return parser.parse_args()


def month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    start = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
    return start, end


def iso_bound(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fetch_dicts(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def trade_rows(conn: sqlite3.Connection, start: str, end: str) -> list[dict[str, Any]]:
    return fetch_dicts(
        conn,
        """
        SELECT
            timestamp AS "时间UTC",
            investor_id AS "投资者",
            action AS "决策类型",
            gold_price AS "交易金价",
            entry_price AS "开仓价",
            exit_price AS "平仓价",
            margin_committed AS "margin",
            tp AS "TP",
            sl AS "SL",
            cash_after AS "交易后现金",
            total_assets_after AS "资产记录",
            nominal_pnl AS "名义盈亏",
            net_pnl AS "净盈亏",
            fees_total AS "费用合计",
            trigger_reason AS "触发原因",
            signal_strength AS "信号强度",
            signal_type AS "信号类型",
            reasoning AS "决策理由"
        FROM trade_history
        WHERE investor_id IN ('A', 'B')
          AND timestamp >= ?
          AND timestamp < ?
        ORDER BY timestamp ASC, investor_id ASC, id ASC
        """,
        (start, end),
    )


def snapshot_rows(conn: sqlite3.Connection, start: str, end: str) -> list[dict[str, Any]]:
    return fetch_dicts(
        conn,
        """
        SELECT
            timestamp AS "时间UTC",
            investor_id AS "投资者",
            total_assets AS "资产记录",
            action AS "持仓动作"
        FROM investor_snapshots
        WHERE investor_id IN ('A', 'B')
          AND timestamp >= ?
          AND timestamp < ?
        ORDER BY timestamp ASC, investor_id ASC, id ASC
        """,
        (start, end),
    )


def current_state_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return fetch_dicts(
        conn,
        """
        SELECT
            investor_id AS "投资者",
            current_action AS "当前决策类型",
            total_assets AS "当前总资产",
            cash AS "现金",
            margin_committed AS "margin",
            entry_price AS "开仓价",
            current_price AS "当前金价",
            tp AS "TP",
            sl AS "SL",
            nominal_pnl AS "名义盈亏",
            net_pnl AS "净盈亏",
            updated_at AS "更新时间UTC"
        FROM investor_state
        WHERE investor_id IN ('A', 'B')
        ORDER BY investor_id ASC
        """,
        (),
    )


def decision_rows(data_dir: Path, start_dt: datetime, end_dt: datetime) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pattern = f"orders_processed_{start_dt:%Y%m}*.json"
    for path in sorted(data_dir.glob(pattern)):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        ts = parse_ts(payload.get("timestamp"))
        if ts is None or not (start_dt <= ts < end_dt):
            continue
        for item in payload.get("instructions", []):
            if item.get("investor") not in {"A", "B"}:
                continue
            rows.append(
                {
                    "决策时间UTC": payload.get("timestamp"),
                    "投资者": item.get("investor"),
                    "决策类型": item.get("action"),
                    "margin_pct": item.get("margin_pct"),
                    "TP": item.get("tp"),
                    "SL": item.get("sl"),
                    "信号强度": item.get("signal_strength"),
                    "信号类型": item.get("signal_type"),
                    "决策理由": item.get("reasoning"),
                    "来源文件": path.name,
                }
            )
    return rows


def rows_to_table(headers: list[str], rows: list[dict[str, Any]]) -> list[list[Any]]:
    table = [headers]
    for row in rows:
        table.append([row.get(header) for header in headers])
    return table


def main() -> None:
    args = parse_args()
    start_dt, end_dt = month_bounds(args.year, args.month)
    start, end = iso_bound(start_dt), iso_bound(end_dt)
    output = args.output or EXPORT_DIR / f"goldclaw_A_B_{args.year}-{args.month:02d}.xlsx"

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        trades = trade_rows(conn, start, end)
        snapshots = snapshot_rows(conn, start, end)
        current = current_state_rows(conn)
    finally:
        conn.close()

    decisions = decision_rows(args.data_dir, start_dt, end_dt)
    summary = [
        ["项目", "值"],
        ["数据库", str(args.db)],
        ["数据目录", str(args.data_dir)],
        ["导出月份", f"{args.year}-{args.month:02d}"],
        ["时间范围UTC", f"{start} <= timestamp < {end}"],
        ["交易流水条数", len(trades)],
        ["资产快照条数", len(snapshots)],
        ["OpenClaw决策条数", len(decisions)],
        ["说明", "5月 hold 决策不会写入 trade_history；本文件另列 OpenClaw 决策和资产快照。"],
    ]
    sheets = [
        ("说明", summary),
        ("交易流水", rows_to_table(
            ["时间UTC", "投资者", "决策类型", "交易金价", "开仓价", "平仓价", "margin", "TP", "SL",
             "交易后现金", "资产记录", "名义盈亏", "净盈亏", "费用合计", "触发原因", "信号强度", "信号类型", "决策理由"],
            trades,
        )),
        ("资产快照", rows_to_table(["时间UTC", "投资者", "资产记录", "持仓动作"], snapshots)),
        ("OpenClaw决策", rows_to_table(
            ["决策时间UTC", "投资者", "决策类型", "margin_pct", "TP", "SL", "信号强度", "信号类型", "决策理由", "来源文件"],
            decisions,
        )),
        ("当前状态", rows_to_table(
            ["投资者", "当前决策类型", "当前总资产", "现金", "margin", "开仓价", "当前金价",
             "TP", "SL", "名义盈亏", "净盈亏", "更新时间UTC"],
            current,
        )),
    ]
    write_xlsx(output, sheets)
    print(output)
    print(f"trades={len(trades)} snapshots={len(snapshots)} decisions={len(decisions)}")


if __name__ == "__main__":
    main()
