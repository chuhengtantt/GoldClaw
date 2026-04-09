"""
OpenClaw Bridge — 门铃接收器。

极简 FastAPI 服务，接收 GoldClaw 的紧急 POST 通知，
然后拉起一次 OpenClaw 会话处理紧急事件。

启动：
    uvicorn openclaw_bridge:app --host 0.0.0.0 --port 8088

GoldClaw 侧 .env 配置：
    GOLDCLAW_OPENCLAW_BRIDGE_URL=http://localhost:8088/emergency
"""

import json
import logging
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("openclaw_bridge")

app = FastAPI(title="OpenClaw Bridge")

# 指向 GoldClaw 的 data/ 目录（默认同项目的 data/）
DATA_DIR = Path(__file__).parent / "data"

# OpenClaw 触发命令：通过 openclaw agent CLI 唤醒 OpenClaw 会话
# 消息会由 _trigger_openclaw 动态拼接后追加为最后一个参数
OPENCLAW_TRIGGER_CMD: list[str] = [
    "openclaw", "agent", "--deliver",
    "-m",  # placeholder, message will be appended by _trigger_openclaw
]


@app.post("/emergency")
async def emergency(request: Request) -> JSONResponse:
    """
    接收 GoldClaw 的门铃通知。

    收到后：
    1. 记录紧急事件到 data/bridge_events.jsonl
    2. 更新 state_for_openclaw.json 中的紧急标记
    3. 触发 OpenClaw 会话（如果配置了命令）
    """
    payload = await request.json()
    event = payload.get("event", "unknown")
    investor = payload.get("investor", "")
    price = payload.get("gold_price", 0)
    message = payload.get("message", "")

    logger.info(
        "Emergency received: event=%s, investor=%s, price=$%.2f",
        event, investor, price,
    )

    # 记录紧急事件到 comm_log 表
    _log_to_db(payload)

    # 1. 记录事件
    _log_event(payload)

    # 2. 触发 OpenClaw（如果配置了）
    if OPENCLAW_TRIGGER_CMD:
        _trigger_openclaw(event, payload)
    else:
        logger.info(
            "No OPENCLAW_TRIGGER_CMD configured. "
            "OpenClaw will pick up state on next cron cycle."
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "received",
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "Bridge received. OpenClaw will process on next cycle.",
        },
    )


@app.get("/health")
async def health() -> JSONResponse:
    """健康检查。"""
    return JSONResponse({"status": "ok"})


def _log_event(payload: dict) -> None:
    """将紧急事件追加到 bridge_events.jsonl。"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log_file = DATA_DIR / "bridge_events.jsonl"

    entry = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        **payload,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _log_to_db(payload: dict) -> None:
    """将紧急事件写入 comm_log 表。"""
    db_path = DATA_DIR / "goldclaw.db"
    if not db_path.exists():
        return
    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO comm_log (direction, event_type, payload, created_at) "
            "VALUES (?, ?, ?, ?)",
            (
                "goldclaw→openclaw",
                "emergency",
                json.dumps(payload, ensure_ascii=False),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning("Failed to log emergency to DB: %s", e)


def _trigger_openclaw(event: str, payload: dict) -> None:
    """触发 OpenClaw 会话，拼接完整的紧急消息。"""
    investor = payload.get("investor", "")
    price = payload.get("gold_price", 0)
    message = payload.get("message", "")
    priority = payload.get("priority", "normal")

    # 拼接描述性消息
    parts = [f"[GoldClaw 紧急通知] 事件: {event}"]
    if investor:
        parts.append(f"投资者: {investor}")
    if price:
        parts.append(f"当前金价: ${price:,.2f}")
    if message:
        parts.append(f"详情: {message}")
    if priority:
        parts.append(f"优先级: {priority}")

    full_message = " | ".join(parts)
    cmd = OPENCLAW_TRIGGER_CMD + [full_message]
    logger.info("Triggering OpenClaw: %s", cmd)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("OpenClaw triggered successfully")
        else:
            logger.error(
                "OpenClaw failed: rc=%d, stderr=%s",
                result.returncode, result.stderr[:500],
            )
    except subprocess.TimeoutExpired:
        logger.error("OpenClaw trigger timed out (120s)")
    except Exception as e:
        logger.error("OpenClaw trigger error: %s", e)


if __name__ == "__main__":
    import uvicorn

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8088
    uvicorn.run(app, host="0.0.0.0", port=port)
