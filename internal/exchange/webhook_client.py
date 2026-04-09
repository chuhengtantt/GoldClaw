"""
GoldClaw 通信层 — 信箱（文件交换）+ 门铃（HTTP POST）。

信箱：每 tick 写状态文件 + 读决策文件
门铃：TRIGGER 时 POST 到 Bridge URL（可选）
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from config.settings import settings
from internal.exchange.schema import (
    EmergencyPayload,
    InvestorInstruction,
    OrderFile,
    StateReport,
)

logger = logging.getLogger(__name__)

STATE_FILE = "data/state_for_openclaw.json"
ORDERS_FILE = "data/orders_from_openclaw.json"
PROCESSED_PREFIX = "data/orders_processed_"


# ============================================================
# 信箱输出：写状态文件
# ============================================================

def write_state_file(report: StateReport) -> None:
    """将状态报告覆写到 state_for_openclaw.json。"""
    path = Path(STATE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    report.timestamp = datetime.now(timezone.utc).isoformat()
    path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    logger.debug("State file written: %s", path)


def build_state_report(
    conn: object,
    system_state: str,
    gold_price: float,
    volatility: float,
    slope: float,
    warnings: list[dict] | None = None,
) -> StateReport:
    """从数据库构建状态报告。"""
    from internal.db.repository import InvestorRepository

    repo = InvestorRepository(conn)

    investors = {}
    for inv_id in ("A", "B"):
        try:
            row = repo.get(inv_id)
            from internal.exchange.schema import InvestorStateReport
            investors[inv_id] = InvestorStateReport(
                total_assets=row["total_assets"],
                cash=row["cash"],
                margin_committed=row["margin_committed"],
                current_action=row["current_action"],
                entry_price=row["entry_price"],
                current_price=row["current_price"] or gold_price,
                tp=row["tp"],
                sl=row["sl"],
                nominal_pnl=row["nominal_pnl"],
                net_pnl=row["net_pnl"],
                margin_call=row["margin_call"],
                pnl_pct=row["pnl_pct"],
                nights_held=row["nights_held"],
            )
        except ValueError:
            continue

    from internal.exchange.schema import SystemReport, WarningReport
    warn_list = []
    if warnings:
        for w in warnings[:5]:  # 最近 5 条
            warn_list.append(WarningReport(**w))

    return StateReport(
        system=SystemReport(
            state=system_state,
            gold_price=gold_price,
            volatility=volatility,
            slope_3min=slope,
        ),
        investors=investors,
        warnings=warn_list,
    )


# ============================================================
# 信箱输入：读决策文件
# ============================================================

def read_orders_file() -> OrderFile | None:
    """
    读取 orders_from_openclaw.json。
    如果文件存在且有效，读取后重命名为 orders_processed_[ts].json。
    返回 None 表示无新决策。
    """
    path = Path(ORDERS_FILE)
    if not path.exists():
        return None

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        orders = OrderFile(**raw)

        # 重命名防止重复读取
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        processed_path = Path(f"{PROCESSED_PREFIX}{ts}.json")
        path.rename(processed_path)
        logger.info("Orders file processed: %s → %s", path, processed_path)

        return orders
    except Exception as e:
        logger.error("Failed to read orders file: %s", e)
        return None


# ============================================================
# 门铃：POST 到 Bridge
# ============================================================

def ring_doorbell(payload: EmergencyPayload) -> bool:
    """
    按门铃：POST 到 Bridge URL。
    URL 未配置时跳过。成功返回 True，失败返回 False（不抛异常）。
    """
    url = settings.openclaw_bridge_url
    if not url:
        logger.debug("Bridge URL not configured, skipping doorbell")
        return False

    payload.timestamp = datetime.now(timezone.utc).isoformat()
    timeout = settings.openclaw_bridge_timeout

    try:
        resp = httpx.post(url, json=payload.model_dump(), timeout=timeout)
        resp.raise_for_status()
        logger.info("Doorbell rang: event=%s", payload.event)
        return True
    except httpx.HTTPError as e:
        logger.warning("Doorbell failed: %s", e)
        return False
