# GoldClaw Dashboard 开发计划

## 0. 原型简图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  GoldClaw                                                    [日志清除 ▼]  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────────────────────────┐  ┌────────────────────────────────┐  │
│  │  金价记录折线图                    │  │  投资者 A — 趋势收割者          │  │
│  │                                  │  │  ─────────────────────────────  │  │
│  │     ╱╲      ╱╲                   │  │  时间    资产   决策  Mgn TP SL │  │
│  │    ╱  ╲    ╱  ╲    ╱╲            │  │  ─────────────────────────────  │  │
│  │───╱────╲──╱────╲──╱──╲──         │  │  12:00  $10,240  long  50% .. │  │
│  │        ╲╱      ╲╱    ╲           │  │  11:45  $10,180  long  50% .. │  │
│  │  $4,750 ─────────────────        │  │  11:30  $10,100  hold  --  .. │  │
│  │                                  │  │  ─────────────────────────────  │  │
│  │  [日视图]  [周视图]  [月视图]      │  │            < 1/5 >            │  │
│  └──────────────────────────────────┘  └────────────────────────────────┘  │
│                                        ┌────────────────────────────────┐  │
│                                        │  投资者 B — 防御性狙击手          │  │
│                                        │  ─────────────────────────────  │  │
│                                        │  时间    资产   决策  Mgn TP SL │  │
│                                        │  ─────────────────────────────  │  │
│                                        │  12:00  $10,050  sgln  --  .. │  │
│                                        │  11:45  $10,020  sgln  --  .. │  │
│                                        │  11:30  $10,000  idle  --  .. │  │
│                                        │  ─────────────────────────────  │  │
│                                        │            < 1/3 >            │  │
│                                        └────────────────────────────────┘  │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  通讯状态监控面板                                                              │
│  ═══════════════════════════════════════════════════════════════════════════ │
│                                                                             │
│  ┌───────────────────────┐    ┌───────────────────────────────────────┐    │
│  │  GoldClaw              │    │  OpenClaw                              │    │
│  │  ─────────────────     │    │  ─────────────────────                │    │
│  │                       │    │                                       │    │
│  │  14:00  ● TICK  $4764 │───▶│  14:00  收到状态报告 → 进入决策          │    │
│  │  13:45  ● TICK  $4760 │    │  13:45  冷却期                        │    │
│  │  13:30  ● TRIGGER     │───▶│  13:30  🚨 紧急触发 → 分析下单          │    │
│  │        状态机 WATCH→   │    │                                       │    │
│  │        TRIGGER         │◀───│  13:30  下发指令: A=cfd_long          │    │
│  │  13:15  ● TICK  $4755 │    │                                       │    │
│  │  13:00  ● IDLE→WATCH  │    │  13:00  冷却期                        │    │
│  │                       │    │                                       │    │
│  └───────────────────────┘    └───────────────────────────────────────┘    │
│                                                                             │
│  ──● Active   ──○ Passive   ──▶ Data Flow   ──🚨 Emergency                │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. 概述

为 GoldClaw 创建一个基于 Web 的监控面板，实时展示金价走势、投资者状态、交易记录、
以及 GoldClaw ↔ OpenClaw 之间的通讯流。

**设计规范**: 遵循 Revolut 风格设计系统（见 `reference/page_design_rules.md`）。
- 近黑 `#191c1f` + 白色为基调，无阴影
- Aeonik Pro / Inter 字体族
- Pill 按钮 (9999px radius)，12px/20px 圆角卡片
- 8px 间距基准

---

## 2. 技术选型

| 层级 | 选择 | 理由 |
|------|------|------|
| 后端 API | FastAPI（扩展现有 bridge） | 项目已有 FastAPI 依赖 |
| 数据库 | SQLite（现有） | 无需新增依赖 |
| 前端 | 单页 HTML + vanilla JS + Chart.js | 轻量，无需构建工具 |
| 样式 | CSS 变量 + 自定义（Revolut 风格） | 无额外 UI 框架 |
| 自动刷新 | 轮询 (fetch + setInterval) | 简单可靠 |

---

## 3. 数据库变更

### 3.1 新增 `price_ticks` 表

> **原因**: 当前 `PriceHistory` 仅存内存（deque 1000），重启即丢失。
> 需要持久化价格数据以支持日/周/月视图。

```sql
CREATE TABLE IF NOT EXISTS price_ticks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    price      REAL NOT NULL,
    source     TEXT DEFAULT '',
    tick_time  TEXT NOT NULL,           -- ISO 8601 UTC
    volatility REAL DEFAULT 0,
    slope      REAL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_price_ticks_time ON price_ticks(tick_time);
```

### 3.2 新增 `comm_log` 表

> **原因**: 当前通讯日志分散在 `bridge_events.jsonl` 和 `goldclaw.log`，
> 需要结构化存储以供面板展示。

```sql
CREATE TABLE IF NOT EXISTS comm_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    direction   TEXT NOT NULL,          -- 'goldclaw→openclaw' | 'openclaw→goldclaw'
    event_type  TEXT NOT NULL,          -- 'tick' | 'state_change' | 'emergency' | 'order' | 'status_report'
    payload     TEXT DEFAULT '{}',      -- JSON 详情
    created_at  TEXT NOT NULL           -- ISO 8601 UTC
);
CREATE INDEX IF NOT EXISTS idx_comm_log_time ON comm_log(created_at);
```

### 3.3 迁移方式

在 `internal/db/migrations.py` 的 `MIGRATIONS` 列表追加两条 DDL，保持幂等。

---

## 4. 后端 API 设计

在现有 `openclaw_bridge.py` 的 FastAPI app 上挂载 `/api` 路由组，
或创建独立的 `dashboard_api.py` 模块。

### 4.1 金价相关

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/prices` | 获取价格历史，支持 `?range=day\|week\|month` |
| `GET` | `/api/prices/latest` | 最新一个 tick |

**响应示例**:
```json
{
  "range": "day",
  "data": [
    {"time": "2026-04-09T12:00:00Z", "price": 4757.40, "volatility": 0.003, "slope": 0.001},
    ...
  ]
}
```

### 4.2 投资者相关

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/investors` | 所有投资者当前状态 |
| `GET` | `/api/investors/{id}/trades` | 交易历史，支持 `?page=1&size=20` |
| `GET` | `/api/investors/{id}/snapshots` | 投资者状态时间线（用于表格翻页）|

**投资者状态响应**:
```json
{
  "investors": {
    "A": {
      "total_assets": 10240.0,
      "cash": 5240.0,
      "margin_committed": 5000.0,
      "current_action": "cfd_long",
      "entry_price": 4748.10,
      "current_price": 4764.60,
      "tp": 4800.0,
      "sl": 4720.0,
      "nominal_pnl": 324.0,
      "net_pnl": 280.0,
      "pnl_pct": 2.8,
      "nights_held": 1
    },
    "B": { ... }
  }
}
```

### 4.3 通讯状态

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/comm` | 通讯日志，支持 `?page=1&size=50` |
| `GET` | `/api/comm/stats` | 通讯统计（最后通讯时间、成功率）|

### 4.4 系统状态

| Method | Path | 说明 |
|--------|------|------|
| `GET` | `/api/system` | 系统状态（状态机、当前金价、波动率）|

### 4.5 日志管理

| Method | Path | 说明 |
|--------|------|------|
| `DELETE` | `/api/logs/price_ticks` | 清除指定日期之前的价格 tick |
| `DELETE` | `/api/logs/comm_log` | 清除指定日期之前的通讯日志 |
| `GET` | `/api/logs/stats` | 各表行数统计（用于判断是否需要清理）|

**清除请求体**:
```json
{
  "before": "2026-04-01T00:00:00Z",
  "table": "price_ticks"
}
```

---

## 5. 前端页面设计

### 5.1 文件结构

```
dashboard/
├── index.html          # 单页入口
├── static/
│   ├── style.css       # Revolut 风格样式
│   ├── app.js          # 主逻辑 + API 调用
│   └── vendor/
│       └── chart.min.js # Chart.js CDN fallback
```

### 5.2 页面布局 (Grid)

```
┌──────────────────────────────────────────────────────────┐
│ Header: GoldClaw Dashboard             [日志管理] [刷新]  │  ← 64px
├────────────────────────────┬─────────────────────────────┤
│                            │  投资者 A 卡片               │
│  金价折线图                 │  (表格 + 分页)              │  ← flex
│  (Chart.js line)           ├─────────────────────────────┤
│  [日|周|月] 切换            │  投资者 B 卡片               │
│                            │  (表格 + 分页)              │
├────────────────────────────┴─────────────────────────────┤
│  通讯状态面板                                              │  ← 底部
│  GoldClaw 列  ←→  OpenClaw 列                             │
└──────────────────────────────────────────────────────────┘
```

### 5.3 样式规范 (CSS 变量)

```css
:root {
  /* Revolut 风格 */
  --color-dark: #191c1f;
  --color-white: #ffffff;
  --color-surface: #f4f4f4;
  --color-border: #c9c9cd;
  --color-muted: #8d969e;
  --color-secondary: #505a63;

  /* 语义色 */
  --color-success: #00a87e;    /* teal - 盈利 */
  --color-danger: #e23b4a;     /* red - 亏损 */
  --color-warning: #ec7e00;    /* orange - TRIGGER */
  --color-info: #494fdf;       /* blue - 通讯活跃 */

  /* 圆角 */
  --radius-sm: 12px;
  --radius-card: 20px;
  --radius-pill: 9999px;

  /* 字体 */
  --font-display: 'Inter', -apple-system, sans-serif;  /* Aeonik Pro 不可用时的降级 */
  --font-body: 'Inter', -apple-system, sans-serif;

  /* 间距 */
  --space-unit: 8px;
}
```

### 5.4 组件详细设计

#### A. 金价折线图

- 使用 Chart.js Line Chart
- 黑色线条 `#191c1f`，无填充
- X 轴: 时间；Y 轴: 金价
- 日/周/月按钮组 (pill 样式)
- 自动刷新间隔: 与系统 tick 频率一致

#### B. 投资者卡片

每个卡片包含:
- **标题**: "投资者 A — 趋势收割者" / "投资者 B — 防御性狙击手"
- **摘要行**: 总资产、当前 PnL（绿/红色）、持仓状态 badge
- **表格**: 列 — 时间 | 资产 | 决策 | Margin | TP | SL
- **分页**: `< 1/5 >` pill 样式

#### C. 通讯状态面板

双列时间轴:
- **左列 (GoldClaw)**: tick 事件、状态机变化、紧急事件
- **右列 (OpenClaw)**: 收到报告、决策下发、冷却期
- **中间**: 连接线/箭头，表示数据流向
- **颜色编码**:
  - `#191c1f` — 正常 tick
  - `#ec7e00` — TRIGGER / 紧急事件
  - `#494fdf` — 数据传输（箭头）
  - `#c9c9cd` — 冷却期 / 空闲

#### D. 日志清除弹窗

- 选择表: `price_ticks` / `comm_log`
- 选择保留范围: 最近 7 天 / 30 天 / 全部清除
- 显示当前行数统计
- 确认后调用 DELETE API

---

## 6. 代码变更清单

### 后端 (Python)

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `internal/db/migrations.py` | 修改 | 追加 `price_ticks`、`comm_log` 建表 |
| 2 | `app/engine.py` | 修改 | tick 内追加写入 `price_ticks`、`comm_log` |
| 3 | `internal/exchange/webhook_client.py` | 修改 | 写信箱/读指令时记录 `comm_log` |
| 4 | `openclaw_bridge.py` | 修改 | 追加通讯事件到 `comm_log` |
| 5 | `dashboard_api.py` | **新建** | Dashboard REST API 路由 |
| 6 | `internal/db/repository.py` | 修改 | 追加价格查询、通讯日志查询方法 |

### 前端 (HTML/CSS/JS)

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 7 | `dashboard/index.html` | **新建** | 单页入口 |
| 8 | `dashboard/static/style.css` | **新建** | Revolut 风格样式 |
| 9 | `dashboard/static/app.js` | **新建** | 主逻辑、API 调用、Chart.js 配置 |

---

## 7. 实施步骤

### Phase 1: 数据持久化 (后端基础)

1. **追加数据库迁移** — `price_ticks` + `comm_log` 建表
2. **修改 Engine tick 循环** — 每次 tick 写入 `price_ticks`
3. **修改通讯模块** — 信箱读写、门铃事件时写入 `comm_log`
4. **编写测试** — 确保新表写入和查询正确

### Phase 2: Dashboard API

5. **创建 `dashboard_api.py`** — 挂载 `/api/*` 路由
6. **实现价格 API** — `/api/prices` + range 过滤
7. **实现投资者 API** — 状态 + 交易历史分页
8. **实现通讯 API** — `comm_log` 查询 + 分页
9. **实现日志管理 API** — 统计 + 清除
10. **合并启动** — 将 dashboard API 与 bridge 同进程运行

### Phase 3: 前端页面

11. **创建 `dashboard/` 目录和文件**
12. **实现 HTML 骨架 + CSS 样式**（Revolut 风格）
13. **实现金价折线图**（Chart.js）
14. **实现投资者卡片 + 表格 + 分页**
15. **实现通讯状态面板**（双列时间轴）
16. **实现日志清除弹窗**
17. **添加自动刷新**

### Phase 4: 联调 & 测试

18. **端到端测试** — 启动 engine + dashboard，验证数据流
19. **响应式适配** — 移动端布局
20. **性能优化** — 大量数据下的分页和图表渲染

---

## 8. 启动方式

```bash
# 方式 1: 仅启动 Dashboard API（从已有 DB 读取数据）
python -m dashboard_api

# 方式 2: Engine + Dashboard 同进程
python main.py --with-dashboard

# 访问
open http://localhost:8088/dashboard/
```

---

## 9. 注意事项

1. **SQLite 并发**: Dashboard 读 + Engine 写可能冲突，使用 WAL 模式（已开启）和
   读事务来避免。
2. **数据量控制**: `price_ticks` 每 3-15 分钟一条，一天约 100-500 条。
   建议设置定时清理策略（保留最近 90 天）。
3. **无 Aeonik Pro**: 前端使用 Inter 作为降级字体（Google Fonts CDN），
   视觉效果接近。
4. **安全**: Dashboard API 仅监听 localhost，不暴露到公网。
