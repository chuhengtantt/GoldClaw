"""
GoldClaw 金价获取模块 — HTTP 客户端 + 重试逻辑。
"""

import logging
import time

import httpx

from config.settings import settings
from internal.exception.errors import PriceFetchError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 0.1


def fetch_gold_price(
    client: httpx.Client | None = None,
    url: str | None = None,
    timeout: float | None = None,
) -> tuple[float, str]:
    """
    获取实时金价。

    Args:
        client: 可选的 httpx.Client（不传则自动创建）。
        url: 可选的 API URL。
        timeout: 可选的超时秒数。

    Returns:
        (price, source) 金价浮点数 + 数据来源标识。

    Raises:
        PriceFetchError: 3 次重试后仍然失败。
    """
    api_url = url or settings.gold_api_url
    api_timeout = timeout or settings.gold_api_timeout

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if client is not None:
                resp = client.get(api_url, timeout=api_timeout)
            else:
                resp = httpx.get(api_url, timeout=api_timeout)

            resp.raise_for_status()
            data = resp.json()
            price = float(data["price"])

            if price <= 0:
                raise ValueError(f"Invalid price: {price}")

            source = data.get("updatedAt", "")
            logger.info("Gold price fetched: $%.2f (source: %s)", price, source)
            return price, source

        except (httpx.HTTPError, ValueError, KeyError) as e:
            logger.warning(
                "Gold price fetch attempt %d/%d failed: %s", attempt, MAX_RETRIES, e
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    raise PriceFetchError(f"Gold API failed after {MAX_RETRIES} retries")
