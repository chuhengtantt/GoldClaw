"""
GoldClaw 默认常量。
"""

# API
MAX_RETRIES = 3
RETRY_DELAY = 0.1  # 秒

# Database
MAX_PRICE_HISTORY = 1000       # 保留最近 1000 个 tick
MAX_TRADE_HISTORY = 10000      # 保留最近 10000 条

# Hallucination Detection
HALLUCINATION_THRESHOLD = 0.5  # total_assets 变化超过 50% 视为幻觉

# Investor Constraints
MAX_POSITIONS = 1              # 每个投资者同时最多持仓数

# Performance
MAX_TICK_SECONDS = 5           # 单次 tick 执行时间上限
MAX_DB_SIZE_MB = 100           # 数据库文件大小上限
