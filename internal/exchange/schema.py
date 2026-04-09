"""
GoldClaw 通信 Schema — Pydantic 严格校验模型。

信箱输出：state_for_openclaw.json（Python → OpenClaw）
信箱输入：orders_from_openclaw.json（OpenClaw → Python）
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 信箱输入：OpenClaw → Python（决策校验）
# ============================================================

class InvestorInstruction(BaseModel):
    """OpenClaw 单条投资指令的校验模型。"""
    investor: str = Field(pattern=r"^[A-Z]$")
    action: str = Field(pattern=r"^(cfd_long|cfd_short|sgln_long|hold|idle|close)$")
    margin_pct: float = Field(ge=0.0, le=1.0, default=0.0)
    tp: float = Field(ge=0.0, default=0.0)
    sl: float = Field(ge=0.0, default=0.0)
    signal_strength: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    signal_type: Optional[str] = Field(default=None, max_length=200)
    reasoning: Optional[str] = Field(default=None, max_length=1000)


class OrderFile(BaseModel):
    """orders_from_openclaw.json 的校验模型。"""
    timestamp: str = ""
    instructions: list[InvestorInstruction] = Field(default_factory=list)


# ============================================================
# 信箱输出：Python → OpenClaw（状态报告）
# ============================================================

class InvestorStateReport(BaseModel):
    """单个投资者的状态摘要。"""
    total_assets: float = 0
    cash: float = 0
    margin_committed: float = 0
    current_action: str = "idle"
    entry_price: Optional[float] = None
    current_price: float = 0
    tp: float = 0
    sl: float = 0
    nominal_pnl: float = 0
    net_pnl: float = 0
    margin_call: int = 0
    pnl_pct: float = 0
    nights_held: int = 0


class SystemReport(BaseModel):
    """系统状态摘要。"""
    state: str = "IDLE"
    gold_price: float = 0
    volatility: float = 0
    slope_3min: float = 0


class WarningReport(BaseModel):
    """违规警告（耻辱柱）。"""
    timestamp: str = ""
    investor: str = ""
    violation: str = ""
    original_action: str = ""
    action_taken: str = ""


class StateReport(BaseModel):
    """state_for_openclaw.json 的完整模型。"""
    type: str = "status_report"
    timestamp: str = ""
    system: SystemReport = Field(default_factory=SystemReport)
    investors: dict[str, InvestorStateReport] = Field(default_factory=dict)
    warnings: list[WarningReport] = Field(default_factory=list)


# ============================================================
# 门铃：TRIGGER 时 POST 到 Bridge
# ============================================================

class EmergencyPayload(BaseModel):
    """紧急通知 payload（门铃 POST）。"""
    type: str = "emergency"
    event: str = ""       # margin_call / stop_loss / take_profit / state_trigger
    priority: str = "urgent"
    timestamp: str = ""
    investor: str = ""
    gold_price: float = 0
    action_taken: str = ""
    message: str = ""
