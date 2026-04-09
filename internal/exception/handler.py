"""
GoldClaw 错误处理器。

标准 tick 错误处理模式：具体错误优先，通用兜底。
"""

import logging
import sqlite3

import httpx

from internal.exception.errors import (
    GoldClawError,
    MarginCallError,
    PriceFetchError,
    WebhookDeliveryError,
)

logger = logging.getLogger(__name__)


def handle_tick_error(error: Exception) -> None:
    """处理 tick 循环中的错误。按优先级分类处理。"""
    if isinstance(error, PriceFetchError):
        logger.error("No price data, skipping tick: %s", error)
    elif isinstance(error, MarginCallError):
        logger.critical("Margin call: %s", error)
    elif isinstance(error, sqlite3.Error):
        logger.error("DB error (auto-rollback): %s", error)
    elif isinstance(error, WebhookDeliveryError):
        logger.warning("Communication error: %s", error)
    elif isinstance(error, GoldClawError):
        logger.error("Engine error: %s", error)
    else:
        logger.critical("Unexpected error: %s", error, exc_info=True)
