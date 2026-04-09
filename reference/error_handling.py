"""
GoldClaw 错误处理模式参考
AI 写错误处理时必须照这个模式来。
"""

import logging
import sqlite3
from datetime import datetime, timezone

import httpx
from pydantic import ValidationError

from internal.exception.errors import (
    GoldClawError,
    PriceFetchError,
    InvalidActionError,
    MarginCallError,
    WebhookDeliveryError,
)

logger = logging.getLogger(__name__)


# ============================================================
# 1. API 请求：重试 + 超时 + 回退
# ============================================================

def fetch_gold_price(client: httpx.Client, url: str, timeout: float = 10.0) -> float:
    """获取金价。失败时重试 3 次，全部失败抛出 PriceFetchError。"""
    for attempt in range(3):
        try:
            resp = client.get(url, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            price = float(data["price"])
            if price <= 0:
                raise ValueError(f"Invalid price: {price}")
            return price
        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning("Gold price fetch attempt %d failed: %s", attempt + 1, e)
            if attempt == 2:
                raise PriceFetchError(f"Gold API failed after 3 retries: {e}") from e
    raise PriceFetchError("Unreachable")  # 不会到这里，但类型检查需要


# ============================================================
# 2. Pydantic 校验失败：拒收 + 记录耻辱柱
# ============================================================

def validate_instruction(
    raw_json: dict,
    conn: sqlite3.Connection,
    investor_id: str,
) -> tuple[dict | None, str | None]:
    """
    校验 OpenClaw 指令。
    返回 (合法指令, 错误信息)。合法为 None 表示校验失败。
    校验失败时自动写入 violations 表。
    """
    try:
        instruction = InvestorInstruction(**raw_json)  # noqa: F821
        # 业务规则校验
        if investor_id == "A" and instruction.action == "sgln_long":
            raise InvalidActionError(f"Investor A cannot {instruction.action}")
        if investor_id == "B" and instruction.action == "cfd_long":
            raise InvalidActionError(f"Investor B cannot {instruction.action}")
        return instruction.model_dump(), None
    except ValidationError as e:
        error_msg = f"Format error: {e}"
        _record_violation(conn, investor_id, raw_json.get("action", "unknown"), error_msg)
        return None, error_msg
    except InvalidActionError as e:
        _record_violation(conn, investor_id, raw_json.get("action", "unknown"), str(e))
        return None, str(e)


def _record_violation(
    conn: sqlite3.Connection,
    investor_id: str,
    original_action: str,
    violation: str,
) -> None:
    """写入 violations 表（耻辱柱）。"""
    conn.execute(
        "INSERT INTO violations (timestamp, investor_id, violation, original_action, action_taken) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            datetime.now(timezone.utc).isoformat(),
            investor_id,
            violation,
            original_action,
            "blocked, continued current strategy",
        ),
    )
    logger.error("Violation: investor=%s, action=%s, %s", investor_id, original_action, violation)


# ============================================================
# 3. Webhook：超时即放弃，不重试
# ============================================================

def send_webhook(
    client: httpx.Client,
    url: str,
    payload: dict,
    timeout: float = 30.0,
) -> bool:
    """发送 Webhook。成功返回 True，超时/失败返回 False（不抛异常）。"""
    try:
        resp = client.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        logger.info("Webhook sent: %s", payload.get("type", "unknown"))
        return True
    except httpx.HTTPError as e:
        logger.warning("Webhook failed: %s", e)
        return False


# ============================================================
# 4. 幻觉检测：交易前后数值对比
# ============================================================

def check_hallucination(
    total_assets_before: float,
    total_assets_after: float,
    threshold: float = 0.5,
) -> bool:
    """
    检测数值突变。
    返回 True 表示检测到幻觉（变化超阈值）。
    """
    if total_assets_before == 0:
        return False
    change_ratio = abs(total_assets_after - total_assets_before) / total_assets_before
    return change_ratio > threshold


# ============================================================
# 5. 引擎主循环的错误处理模式
# ============================================================

def tick_example(conn: sqlite3.Connection) -> None:
    """标准 tick 错误处理模式。"""
    try:
        # 1. 获取金价
        price = fetch_gold_price(...)

        # 2. 记录交易前快照
        snapshot_before = get_investor_snapshot(conn, "A")

        # 3. 执行交易逻辑
        with conn:  # 事务
            execute_trade(conn, "A", price, ...)

        # 4. 幻觉检测
        snapshot_after = get_investor_snapshot(conn, "A")
        if check_hallucination(snapshot_before["total_assets"], snapshot_after["total_assets"]):
            logger.critical("Hallucination detected! Rolling back.")
            # 恢复交易前状态
            restore_snapshot(conn, "A", snapshot_before)
            _record_violation(conn, "A", "trade", "Hallucination: assets changed >50%")

    except PriceFetchError:
        logger.error("No price data, skipping tick")
    except MarginCallError as e:
        logger.critical("Margin call: %s", e)
        # 爆仓处理已在异常内部完成
    except sqlite3.Error as e:
        logger.error("DB error: %s", e)
        # with conn 已自动 ROLLBACK
    except GoldClawError as e:
        logger.error("Engine error: %s", e)
    except Exception as e:
        logger.critical("Unexpected error: %s", e, exc_info=True)
