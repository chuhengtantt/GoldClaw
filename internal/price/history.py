"""
GoldClaw 价格历史 — deque 滚动缓冲区。
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class PriceTick:
    """单个价格 tick。"""
    price: float
    timestamp: str  # ISO 8601 UTC
    source: str = ""


class PriceHistory:
    """价格历史缓冲区。保留最近 N 个 tick 的价格数据。"""

    def __init__(self, maxlen: int = 1000) -> None:
        self._ticks: deque[PriceTick] = deque(maxlen=maxlen)

    def add(self, price: float, source: str = "") -> None:
        """添加一个价格 tick。"""
        tick = PriceTick(
            price=price,
            timestamp=datetime.now(timezone.utc).isoformat(),
            source=source,
        )
        self._ticks.append(tick)
        logger.debug("Price tick added: $%.2f, total=%d", price, len(self._ticks))

    @property
    def latest(self) -> PriceTick | None:
        """返回最新的 tick，无数据时返回 None。"""
        return self._ticks[-1] if self._ticks else None

    @property
    def latest_price(self) -> float | None:
        """返回最新价格，无数据时返回 None。"""
        return self._ticks[-1].price if self._ticks else None

    def get_prices(self, n: int | None = None) -> list[float]:
        """返回最近 n 个价格。n=None 返回全部。"""
        ticks = list(self._ticks)
        if n is not None:
            ticks = ticks[-n:]
        return [t.price for t in ticks]

    def get_ticks(self, n: int | None = None) -> list[PriceTick]:
        """返回最近 n 个 tick。n=None 返回全部。"""
        ticks = list(self._ticks)
        if n is not None:
            ticks = ticks[-n:]
        return ticks

    def __len__(self) -> int:
        return len(self._ticks)

    def __bool__(self) -> bool:
        return len(self._ticks) > 0
