"""
GoldClaw 入口 — 启动调度器。

启动流程：
1. 配置日志
2. 初始化引擎（数据库、状态机）
3. 执行首次 tick
4. 启动 APScheduler
5. 等待 Ctrl+C 优雅退出
"""

import logging
import signal
import sys
import time

from app.engine import Engine
from app.scheduler import GoldClawScheduler


def setup_logging() -> None:
    """配置日志格式。"""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main() -> None:
    """启动 GoldClaw。"""
    setup_logging()
    logger = logging.getLogger("goldclaw")
    logger.info("GoldClaw starting...")

    # 初始化引擎
    engine = Engine()
    engine.initialize()

    # 首次 tick
    logger.info("Running initial tick...")
    engine.run_tick()

    # 启动调度器
    scheduler = GoldClawScheduler(engine)
    scheduler.start()
    logger.info("GoldClaw started, state=%s", engine.system_state.value)

    # 优雅退出
    running = True

    def signal_handler(sig: int, frame: object) -> None:
        nonlocal running
        logger.info("Received signal %s, shutting down...", sig)
        running = False

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        while running:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
        engine.shutdown()
        logger.info("GoldClaw stopped gracefully")


if __name__ == "__main__":
    main()
