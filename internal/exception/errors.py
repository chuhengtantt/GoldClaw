"""
GoldClaw 自定义异常。
"""


class GoldClawError(Exception):
    """GoldClaw 基础异常。"""
    pass


class PriceFetchError(GoldClawError):
    """金价获取失败。"""
    pass


class InvalidActionError(GoldClawError):
    """非法操作（如投资者 A 尝试 sgln_long）。"""
    pass


class MarginCallError(GoldClawError):
    """保证金归零（爆仓）。"""
    pass


class WebhookDeliveryError(GoldClawError):
    """Webhook 投递失败。"""
    pass


class HallucinationError(GoldClawError):
    """幻觉检测触发（数值突变超阈值）。"""
    pass
