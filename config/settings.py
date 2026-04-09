"""
GoldClaw 配置管理 — pydantic-settings 从 .env 加载环境变量。
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。从 .env 文件加载，类型安全。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Gold API
    gold_api_url: str = "https://api.gold-api.com/price/XAU"
    gold_api_timeout: float = 10.0

    # OpenClaw Bridge (门铃，可选)
    openclaw_bridge_url: str = ""
    openclaw_bridge_timeout: float = 30.0

    # Database
    db_path: str = "data/goldclaw.db"

    # Scheduler
    schedule_interval_idle: int = 15   # 分钟
    schedule_interval_watch: int = 3   # 分钟

    # State Machine Thresholds
    cycle_x: int = 5
    threshold_a: float = 0.003
    threshold_b: float = 0.005
    watch_duration: int = 5
    trigger_slope: float = 0.002
    silence_period: int = 30           # 分钟

    # Initial Capital
    initial_cash_a: float = 10000.0
    initial_cash_b: float = 10000.0

    @property
    def db_full_path(self) -> Path:
        """返回数据库文件的绝对路径。"""
        return Path(self.db_path)


settings = Settings()
