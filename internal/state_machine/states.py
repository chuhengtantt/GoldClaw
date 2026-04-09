"""
GoldClaw 状态机枚举。
"""

from enum import Enum


class SystemState(str, Enum):
    """系统状态：IDLE / WATCH / TRIGGER。"""
    IDLE = "IDLE"
    WATCH = "WATCH"
    TRIGGER = "TRIGGER"


class Action(str, Enum):
    """投资动作枚举。"""
    IDLE = "idle"
    HOLD = "hold"
    CFD_LONG = "cfd_long"
    CFD_SHORT = "cfd_short"
    SGLN_LONG = "sgln_long"
    CLOSE = "close"
