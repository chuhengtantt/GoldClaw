"""
GoldClaw macOS App 入口 — PyInstaller 打包用。

功能：
1. 初始化数据库
2. 启动 Engine（后台线程）
3. 启动 Dashboard API（后台 uvicorn）
4. 打开原生 pywebview 窗口（主线程）
"""

import logging
import os
import sys
import threading
import time

import webview


def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def main():
    setup_logging()
    logger = logging.getLogger("goldclaw")

    # 切换到正确的工作目录（PyInstaller bundle）
    if getattr(sys, 'frozen', False):
        # Launcher 脚本 exec Resources/GoldClaw，所以 sys.executable
        # 在 Contents/Resources/ 而非 Contents/MacOS/
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        is_app_bundle = ".app/Contents" in exe_dir
        if is_app_bundle:
            # .app bundle: data 目录放在用户可见的位置
            # ~/GoldClaw/ 方便 OpenClaw 访问
            user_data = os.path.expanduser("~/GoldClaw")
            os.makedirs(user_data, exist_ok=True)
            os.chdir(user_data)
            logger.info("Data dir: %s", user_data)
        else:
            os.chdir(exe_dir)

    logger.info("GoldClaw starting...")
    logger.info("Working dir: %s", os.getcwd())

    # 初始化数据库 + Engine
    from app.engine import Engine
    from app.scheduler import GoldClawScheduler

    engine = Engine()
    engine.initialize()
    engine.run_tick()

    scheduler = GoldClawScheduler(engine)
    engine.set_scheduler(scheduler)
    scheduler.start()
    logger.info("Engine started, state=%s", engine.system_state.value)

    # 启动 Dashboard API（后台线程）
    from dashboard_api import app
    import uvicorn

    port = 8089
    url = f"http://localhost:{port}/dashboard/"
    logger.info("Dashboard: %s", url)

    server_thread = threading.Thread(
        target=uvicorn.run,
        kwargs={"app": app, "host": "0.0.0.0", "port": port, "log_level": "warning"},
        daemon=True,
    )
    server_thread.start()

    # 等待 uvicorn 就绪
    import httpx
    for _ in range(30):
        try:
            httpx.get(f"http://localhost:{port}/health", timeout=0.1)
            break
        except Exception:
            time.sleep(0.1)

    # 关闭窗口时优雅退出
    def on_close():
        logger.info("Window closed, shutting down...")
        scheduler.shutdown()
        engine.shutdown()

    # 原生窗口（主线程，macOS 要求）
    window = webview.create_window(
        title="GoldClaw Dashboard",
        url=url,
        width=1280,
        height=800,
        resizable=True,
        min_size=(960, 600),
    )
    window.events.closing += on_close

    webview.start(debug=False)

    # webview.start() 返回后（窗口已关闭）
    scheduler.shutdown()
    engine.shutdown()
    logger.info("GoldClaw stopped")


if __name__ == "__main__":
    main()
