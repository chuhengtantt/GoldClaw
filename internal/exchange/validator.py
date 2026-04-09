"""
GoldClaw 指令校验 + 幻觉检测 + 耻辱柱。

校验流程：
1. Pydantic 格式校验
2. 投资者权限校验（A 不能 sgln_long，B 不能 cfd_long）
3. 开仓必须提供 margin_pct
4. CFD 开仓必须提供 tp/sl
5. 幻觉检测：交易前后 total_assets 变化超阈值
"""

import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from pydantic import ValidationError

from internal.exception.errors import InvalidActionError
from internal.exchange.schema import InvestorInstruction

logger = logging.getLogger(__name__)

# 投资者允许的 action
INVESTOR_ACTIONS: dict[str, set[str]] = {
    "A": {"cfd_long", "cfd_short", "hold", "idle", "close"},
    "B": {"cfd_short", "sgln_long", "hold", "idle", "close"},
}


def validate_instruction(
    raw_json: dict,
    investor_id: str,
) -> tuple[Optional[InvestorInstruction], Optional[str]]:
    """
    校验单条 OpenClaw 指令。

    Returns:
        (合法指令, 错误信息)。指令为 None 表示校验失败。
    """
    # 1. Pydantic 格式校验
    try:
        instruction = InvestorInstruction(**raw_json)
    except ValidationError as e:
        error_msg = f"Format error: {e}"
        return None, error_msg

    # 2. 投资者权限校验
    allowed = INVESTOR_ACTIONS.get(investor_id, set())
    if instruction.action not in allowed:
        error_msg = f"Investor {investor_id} cannot {instruction.action}"
        return None, error_msg

    # 3. 开仓类必须提供 margin_pct
    open_actions = {"cfd_long", "cfd_short", "sgln_long"}
    if instruction.action in open_actions and instruction.margin_pct <= 0:
        error_msg = f"margin_pct required for {instruction.action}, got {instruction.margin_pct}"
        return None, error_msg

    # 4. CFD 开仓必须提供 tp/sl
    cfd_actions = {"cfd_long", "cfd_short"}
    if instruction.action in cfd_actions:
        if instruction.tp <= 0 or instruction.sl <= 0:
            error_msg = f"tp and sl required for {instruction.action}, got tp={instruction.tp}, sl={instruction.sl}"
            return None, error_msg

    return instruction, None


def validate_orders(
    raw_orders: dict,
) -> tuple[list[tuple[str, InvestorInstruction]], list[tuple[str, str, str]]]:
    """
    批量校验订单文件。

    Returns:
        (有效指令列表[(investor_id, instruction)], 违规列表[(investor_id, action, error)])
    """
    valid: list[tuple[str, InvestorInstruction]] = []
    violations: list[tuple[str, str, str]] = []

    instructions = raw_orders.get("instructions", [])
    for raw in instructions:
        investor_id = raw.get("investor", "?")
        action = raw.get("action", "unknown")
        instruction, error = validate_instruction(raw, investor_id)

        if instruction is not None:
            valid.append((investor_id, instruction))
        else:
            violations.append((investor_id, action, error or "unknown error"))

    return valid, violations


def record_violation(
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
    logger.error(
        "Violation: investor=%s, action=%s, %s", investor_id, original_action, violation
    )


def check_hallucination(
    total_assets_before: float,
    total_assets_after: float,
    threshold: float = 0.5,
) -> bool:
    """检测数值突变。返回 True 表示检测到幻觉。"""
    if total_assets_before == 0:
        return False
    change_ratio = abs(total_assets_after - total_assets_before) / total_assets_before
    return change_ratio > threshold


def get_unacknowledged_violations(
    conn: sqlite3.Connection, limit: int = 5,
) -> list[dict]:
    """获取最近未通报的违规记录。"""
    rows = conn.execute(
        "SELECT timestamp, investor_id as investor, violation, "
        "original_action as original_action, action_taken "
        "FROM violations WHERE acknowledged = 0 "
        "ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()

    # 标记为已通报
    if rows:
        conn.execute("UPDATE violations SET acknowledged = 1 WHERE acknowledged = 0")

    return [dict(r) for r in rows]
