"""
GoldClaw 波动率与斜率计算。
"""

import math


def calc_slope(prices: list[float], window: int | None = None) -> float:
    """
    计算价格序列的线性回归斜率。

    使用最小二乘法拟合 y = a + b*x，返回斜率 b。
    window=None 时使用全部数据，否则取最后 window 个。

    Returns:
        归一化斜率（相对价格均值），便于跨周期比较。
    """
    if window is not None:
        prices = prices[-window:]

    n = len(prices)
    if n < 2:
        return 0.0

    # 最小二乘法
    x_mean = (n - 1) / 2.0
    y_mean = sum(prices) / n

    numerator = 0.0
    denominator = 0.0
    for i, y in enumerate(prices):
        dx = i - x_mean
        dy = y - y_mean
        numerator += dx * dy
        denominator += dx * dx

    if denominator == 0:
        return 0.0

    slope = numerator / denominator

    # 归一化：斜率 / 均价 → 无量纲，便于与阈值比较
    if y_mean == 0:
        return 0.0
    return slope / y_mean


def calc_volatility(prices: list[float], window: int | None = None) -> float:
    """
    计算价格序列的标准差（波动率）。

    Returns:
        归一化波动率（CV = std / mean），无量纲。
    """
    if window is not None:
        prices = prices[-window:]

    n = len(prices)
    if n < 2:
        return 0.0

    mean = sum(prices) / n
    if mean == 0:
        return 0.0

    variance = sum((p - mean) ** 2 for p in prices) / (n - 1)
    return math.sqrt(variance) / mean


def calc_price_change(prices: list[float]) -> float:
    """
    计算最近两个 tick 的价格变化率。

    Returns:
        (current - prev) / prev，无数据时返回 0。
    """
    if len(prices) < 2:
        return 0.0
    prev = prices[-2]
    if prev == 0:
        return 0.0
    return (prices[-1] - prev) / prev
