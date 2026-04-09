"""
GoldClaw Dashboard API — 挂载在 FastAPI 上提供 REST 端点。

与 openclaw_bridge 同进程运行：
    uvicorn dashboard_api:app --host 0.0.0.0 --port 8088

或者 Engine 启动时附带 --with-dashboard。
"""

import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config.settings import settings
from internal.db.connection import get_connection
from internal.db.repository import DashboardRepository

logger = logging.getLogger(__name__)

DASHBOARD_DIR = Path(__file__).parent / "dashboard"

app = FastAPI(title="GoldClaw Dashboard")

# 挂载静态文件
if DASHBOARD_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(DASHBOARD_DIR / "static")), name="static")


# ============================================================
# DB 连接管理
# ============================================================

def _get_repo() -> DashboardRepository:
    conn = get_connection()
    return DashboardRepository(conn)


def _close_conn(repo: DashboardRepository) -> None:
    try:
        repo._conn.close()
    except Exception:
        pass


# ============================================================
# 页面入口
# ============================================================

@app.get("/dashboard/")
@app.get("/dashboard")
async def dashboard_page():
    """返回 Dashboard HTML 页面。"""
    index_path = DASHBOARD_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="Dashboard not built yet")
    return FileResponse(str(index_path))


# ============================================================
# 金价 API
# ============================================================

@app.get("/api/prices")
async def get_prices(range: str = Query("day", pattern="^(day|week|month)$")):
    """获取价格历史。range: day | week | month。"""
    repo = _get_repo()
    try:
        now = datetime.now(timezone.utc)
        if range == "day":
            since = (now - timedelta(days=1)).isoformat()
        elif range == "week":
            since = (now - timedelta(weeks=1)).isoformat()
        else:
            since = (now - timedelta(days=30)).isoformat()

        rows = repo.get_price_ticks(since=since, limit=5000)
        data = [
            {
                "time": row["tick_time"],
                "price": row["price"],
                "volatility": row["volatility"],
                "slope": row["slope"],
            }
            for row in rows
        ]
        return {"range": range, "count": len(data), "data": data}
    finally:
        _close_conn(repo)


@app.get("/api/prices/latest")
async def get_latest_price():
    """获取最新价格 tick。"""
    repo = _get_repo()
    try:
        row = repo.get_latest_tick()
        if not row:
            return {"price": None, "time": None}
        return {
            "price": row["price"],
            "time": row["tick_time"],
            "volatility": row["volatility"],
            "slope": row["slope"],
        }
    finally:
        _close_conn(repo)


# ============================================================
# 投资者 API
# ============================================================

@app.get("/api/investors")
async def get_investors():
    """获取所有投资者当前状态。"""
    repo = _get_repo()
    try:
        rows = repo.get_all_investors()
        investors = {}
        for row in rows:
            inv = dict(row)
            inv_id = inv.pop("investor_id")
            investors[inv_id] = inv
        return {"investors": investors}
    finally:
        _close_conn(repo)


@app.get("/api/investors/{investor_id}/trades")
async def get_trades(
    investor_id: str,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """获取投资者交易历史（分页）。"""
    if investor_id not in ("A", "B"):
        raise HTTPException(status_code=400, detail="investor_id must be A or B")
    repo = _get_repo()
    try:
        rows, total = repo.get_trade_history(investor_id=investor_id, page=page, size=size)
        trades = [dict(row) for row in rows]
        return {
            "investor": investor_id,
            "page": page,
            "size": size,
            "total": total,
            "total_pages": (total + size - 1) // size,
            "trades": trades,
        }
    finally:
        _close_conn(repo)


# ============================================================
# 通讯状态 API
# ============================================================

@app.get("/api/comm")
async def get_comm_log(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
):
    """获取通讯日志（分页）。"""
    repo = _get_repo()
    try:
        rows, total = repo.get_comm_log(page=page, size=size)
        logs = [dict(row) for row in rows]
        return {
            "page": page,
            "size": size,
            "total": total,
            "total_pages": (total + size - 1) // size,
            "logs": logs,
        }
    finally:
        _close_conn(repo)


@app.get("/api/comm/summary")
async def get_comm_summary(
    range: str = Query("week", pattern="^(week|month)$"),
):
    """通讯日志按天聚合。range: week | month。返回每天的 GC→OC / OC→GC 计数。"""
    repo = _get_repo()
    try:
        now = datetime.now(timezone.utc)
        if range == "week":
            since = (now - timedelta(days=7)).isoformat()
        else:
            since = (now - timedelta(days=30)).isoformat()
        data = repo.get_comm_daily_summary(since=since)
        return {"range": range, "days": data}
    finally:
        _close_conn(repo)


# ============================================================
# 系统状态 API
# ============================================================

@app.get("/api/system")
async def get_system():
    """获取系统状态。"""
    repo = _get_repo()
    try:
        row = repo.get_system_state()
        if not row:
            raise HTTPException(status_code=404, detail="System state not found")
        return dict(row)
    finally:
        _close_conn(repo)


# ============================================================
# 日志管理 API
# ============================================================

@app.get("/api/logs/stats")
async def get_log_stats():
    """获取各表行数统计。"""
    repo = _get_repo()
    try:
        return repo.get_table_stats()
    finally:
        _close_conn(repo)


@app.delete("/api/logs/price_ticks")
async def clear_price_ticks(before: str = Query(..., description="ISO 8601 UTC timestamp")):
    """删除指定时间之前的价格 tick。"""
    repo = _get_repo()
    try:
        deleted = repo.delete_price_ticks_before(before)
        return {"deleted": deleted, "before": before}
    finally:
        _close_conn(repo)


@app.delete("/api/logs/comm_log")
async def clear_comm_log(before: str = Query(..., description="ISO 8601 UTC timestamp")):
    """删除指定时间之前的通讯日志。"""
    repo = _get_repo()
    try:
        deleted = repo.delete_comm_log_before(before)
        return {"deleted": deleted, "before": before}
    finally:
        _close_conn(repo)


# ============================================================
# 健康检查（兼容原有 bridge）
# ============================================================

# ============================================================
# 运行时配置 API
# ============================================================

# 默认值（来自 .env / settings）
from config.settings import settings as _settings

CONFIG_DEFAULTS = {
    "trigger_slope": str(_settings.trigger_slope),
    "schedule_interval_idle": str(_settings.schedule_interval_idle),
    "schedule_interval_watch": str(_settings.schedule_interval_watch),
    "threshold_a": str(_settings.threshold_a),
    "threshold_b": str(_settings.threshold_b),
    "silence_period": str(_settings.silence_period),
}

CONFIG_LABELS = {
    "trigger_slope": "触发斜率",
    "schedule_interval_idle": "常规周期 (分钟)",
    "schedule_interval_watch": "异常周期 (分钟)",
    "threshold_a": "阈值 A",
    "threshold_b": "阈值 B",
    "silence_period": "静默期 (分钟)",
}


@app.get("/api/config")
async def get_config():
    """获取运行时配置（合并 DB 覆盖 + 默认值）。"""
    repo = _get_repo()
    try:
        overrides = repo.get_all_config()
        config = {}
        for key, default in CONFIG_DEFAULTS.items():
            config[key] = {
                "value": overrides.get(key, default),
                "default": default,
                "label": CONFIG_LABELS.get(key, key),
            }
        return config
    finally:
        _close_conn(repo)


@app.patch("/api/config")
async def update_config(request: Request):
    """更新运行时配置（立即持久化，下次 tick 生效）。"""
    body = await request.json()
    repo = _get_repo()
    try:
        updated = {}
        for key, value in body.items():
            if key not in CONFIG_DEFAULTS:
                continue
            str_val = str(value)
            repo.set_config(key, str_val)
            updated[key] = str_val
        return {"updated": updated}
    finally:
        _close_conn(repo)


@app.post("/api/config/reset")
async def reset_config():
    """恢复所有配置为默认值。"""
    repo = _get_repo()
    try:
        for key, default in CONFIG_DEFAULTS.items():
            repo.set_config(key, default)
        return {"reset": list(CONFIG_DEFAULTS.keys())}
    finally:
        _close_conn(repo)


@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


# ============================================================
# 启动入口
# ============================================================

if __name__ == "__main__":
    import uvicorn

    port = int(__import__("sys").argv[1]) if len(__import__("sys").argv) > 1 else 8088
    uvicorn.run(app, host="0.0.0.0", port=port)
