"""
GoldClaw 代码风格参考
AI 写新代码时必须照这个风格来。
"""

# ============================================================
# 1. 导入顺序：标准库 → 第三方 → 项目内部
# ============================================================

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from pydantic import BaseModel, Field

from config.settings import settings
from internal.exception.errors import GoldClawError


# ============================================================
# 2. 日志：用 logging，不用 print
# ============================================================

logger = logging.getLogger(__name__)

# 正确
logger.info("Tick completed: XAU $%.2f, state=%s", price, state)
logger.warning("API timeout, using cached price $%.2f", cached_price)
logger.error("Margin call: investor %s, loss $%.2f", investor_id, loss)

# 错误
# print(f"Tick completed: XAU ${price}")  # 不要用 print


# ============================================================
# 3. 类型注解：所有函数签名必须加类型
# ============================================================

def calc_cfd_pnl(
    margin: float,
    entry_price: float,
    current_price: float,
    nights_held: int,
    direction: str = "long",
) -> dict[str, float]:
    """计算 CFD 盈亏。返回包含 actual_margin, nominal_pnl, net_pnl 等的字典。"""
    ...


# ============================================================
# 4. 常量用大写，配置从 settings 读取
# ============================================================

# 模块内硬编码常量
MAX_RETRIES = 3
RETRY_DELAY = 0.1  # 秒

# 可配置的参数从 settings 读
# settings 在 config/settings.py 中定义，从 .env 加载
timeout = settings.gold_api_timeout
url = settings.gold_api_url


# ============================================================
# 5. 数据库操作：永远用事务
# ============================================================

def update_investor_state(conn: sqlite3.Connection, investor_id: str, **kwargs) -> None:
    """更新投资者状态。调用方负责事务管理。"""
    columns = ", ".join(f"{k} = ?" for k in kwargs)
    values = list(kwargs.values()) + [investor_id]
    conn.execute(f"UPDATE investor_state SET {columns} WHERE investor_id = ?", values)


# 调用方式
def example_usage(conn: sqlite3.Connection) -> None:
    try:
        with conn:  # 自动事务
            update_investor_state(conn, "A", cash=5000.0, total_assets=5000.0)
            conn.execute(
                "INSERT INTO trade_history (timestamp, investor_id, action, gold_price) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), "A", "close", 3025.50),
            )
    except sqlite3.Error as e:
        logger.error("DB transaction failed: %s", e)
        # with conn 会自动 ROLLBACK


# ============================================================
# 6. Pydantic Schema：严格校验
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


# ============================================================
# 7. 文件大小：不超过 300 行
# ============================================================

# 如果一个文件快到 300 行，把其中某个功能拆出去新建文件。
# 每个文件单一职责。
