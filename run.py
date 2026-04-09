"""
GoldClaw 一体化启动 — Engine + Dashboard + Bridge 同进程。

用法：
    python run.py              # 启动所有服务
    python run.py --no-engine  # 仅 Dashboard（从已有 DB 读数据）
"""

import logging
import signal
import sys
import threading
import time

import uvicorn


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main() -> None:
    setup_logging()
    logger = logging.getLogger("goldclaw")

    no_engine = "--no-engine" in sys.argv

    # 1. 启动 Engine（后台线程）
    if not no_engine:
        from app.engine import Engine
        from app.scheduler import GoldClawScheduler

        engine = Engine()
        engine.initialize()
        engine.run_tick()

        scheduler = GoldClawScheduler(engine)
        engine.set_scheduler(scheduler)
        scheduler.start()
        logger.info("Engine started, state=%s", engine.system_state.value)
    else:
        engine = None
        scheduler = None
        logger.info("Engine disabled (--no-engine), Dashboard-only mode")

    # 2. 启动 Dashboard API + Bridge（主线程 uvicorn）
    from dashboard_api import app

    port = 8089
    logger.info("Dashboard starting on http://localhost:%d/dashboard/", port)

    # 优雅退出
    original_sigint = signal.getsignal(signal.SIGINT)

    def signal_handler(sig, frame):
        logger.info("Shutting down...")
        if scheduler:
            scheduler.shutdown()
        if engine:
            engine.shutdown()
        # uvicorn 会自己退出
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, signal_handler)

    try:
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
    except KeyboardInterrupt:
        pass
    finally:
        if scheduler:
            scheduler.shutdown()
        if engine:
            engine.shutdown()
        logger.info("GoldClaw stopped gracefully")


if __name__ == "__main__":
    main()
