# GoldClaw

<img width="1280" height="982" alt="telegram-cloud-photo-size-4-5978641587988270154-y" src="https://github.com/user-attachments/assets/17242596-a6b1-4d8c-bdae-6d864c9c5ae3" />
<img width="1280" height="982" alt="telegram-cloud-photo-size-4-5978641587988270154-y" src="https://github.com/user-attachments/assets/b013d811-6315-475a-8544-88cf2d760500" />
<img width="1280" height="982" alt="telegram-cloud-photo-size-4-5978641587988270154-y" src="https://github.com/user-attachments/assets/a022997d-4bd8-4102-a7ab-f1ffac4be189" />
<img width="1280" height="982" alt="telegram-cloud-photo-size-4-5978641587988270154-y" src="https://github.com/user-attachments/assets/362b66c3-088a-4203-84c6-e9879f47d085" />












> 量化黄金交易模拟引擎 + Dashboard — Quantitative Gold Trading Simulation Engine

---

## 这是什么？

GoldClaw 是一个本地运行的 macOS 应用，用于模拟黄金（XAU）交易。它通过实时金价 API 监控市场，接收外部 AI 系统（OpenClaw）的投资指令，自动执行模拟交易的资产计算、止损止盈监控和爆仓检测。

内置 Dashboard 控制面板，提供金价走势图、投资者持仓明细、通讯监控和运行参数配置。

---

## 安装与启动

### 方式一：DMG 安装（推荐）

1. 从 [GitHub Releases](https://github.com/chuhengtantt/GoldClaw/releases) 下载最新 `.dmg`
2. 双击打开，拖 GoldClaw.app 到「应用程序」
3. 双击 GoldClaw.app — 自动打开 Dashboard 窗口
4. 首次打开需在「系统设置 > 隐私与安全性」中允许

### 方式二：源码运行

```bash
git clone https://github.com/chuhengtantt/GoldClaw.git
cd GoldClaw
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 编辑配置
python run.py           # 启动 Engine + Dashboard
```

浏览器打开 http://localhost:8089/dashboard/

---

## Dashboard 功能

| 页面 | 功能 |
|------|------|
| **资产页** | 金价折线图（红涨绿跌）、投资者 A/B 持仓与交易记录 |
| **通讯状态** | GoldClaw ↔ OpenClaw 通讯日志（日/周/月视图） |
| **参数配置** | 运行时修改调度间隔、状态机阈值等参数 |

---

## OpenClaw 通讯协议

GoldClaw 与 OpenClaw 之间采用 **信箱 + 门铃** 双通道通信：

```
┌─────────────┐   state_for_openclaw.json   ┌─────────────┐
│             │ ──────────────────────────► │             │
│  GoldClaw   │                             │  OpenClaw   │
│  (Python)   │ ◄── orders_from_openclaw.json │  (AI Agent) │
│             │                             │             │
│             │   POST /emergency (门铃)     │             │
│             │ ──────────────────────────► │             │
└─────────────┘                             └─────────────┘
```

### 数据目录

| 路径 | 说明 |
|------|------|
| `~/GoldClaw/data/` | 根数据目录 |
| `~/GoldClaw/data/goldclaw.db` | SQLite 数据库 |
| `~/GoldClaw/data/state_for_openclaw.json` | GoldClaw 状态输出（每次 tick 覆写） |
| `~/GoldClaw/data/orders_from_openclaw.json` | OpenClaw 下单指令（GoldClaw 读取后归档） |
| `~/GoldClaw/data/bridge_events.jsonl` | 紧急事件日志 |

### GoldClaw → OpenClaw：状态文件

每次 tick 覆写 `state_for_openclaw.json`：

```json
{
  "type": "status_report",
  "timestamp": "2026-04-09T21:21:31Z",
  "system": {
    "state": "IDLE",
    "gold_price": 4767.50,
    "volatility": 0.00349,
    "slope_3min": -0.00022
  },
  "investors": {
    "A": {
      "total_assets": 10381.89,
      "cash": 7115.97,
      "margin_committed": 3019.20,
      "current_action": "cfd_long",
      "entry_price": 4748.10,
      "current_price": 4767.50,
      "tp": 4850.00,
      "sl": 4680.00,
      "nominal_pnl": 246.72,
      "net_pnl": 245.48,
      "margin_call": 0,
      "pnl_pct": 0.0817,
      "nights_held": 0
    },
    "B": {
      "total_assets": 10000.00,
      "cash": 10000.00,
      "margin_committed": 0,
      "current_action": "idle",
      "entry_price": null,
      "current_price": 4767.50,
      "tp": 0,
      "sl": 0,
      "nominal_pnl": 0,
      "net_pnl": 0,
      "margin_call": 0,
      "pnl_pct": 0,
      "nights_held": 0
    }
  },
  "warnings": []
}
```

### OpenClaw → GoldClaw：下单指令

OpenClaw 写入 `orders_from_openclaw.json`，GoldClaw 在下次 tick 读取并执行：

```json
{
  "timestamp": "2026-04-09T12:00:00Z",
  "instructions": [
    {
      "investor": "A",
      "action": "cfd_long",
      "margin_pct": 0.8,
      "tp": 4850.00,
      "sl": 4680.00,
      "signal_strength": 0.85,
      "signal_type": "strong_bullish",
      "reasoning": "突破关键阻力位，趋势向上"
    },
    {
      "investor": "B",
      "action": "sgln_long",
      "margin_pct": 0.6,
      "tp": 0,
      "sl": 0,
      "reasoning": "对冲风险，配置实物黄金"
    }
  ]
}
```

**字段说明：**

| 字段 | 必填 | 说明 |
|------|------|------|
| `investor` | 是 | 投资者 ID：`"A"` 或 `"B"` |
| `action` | 是 | 操作：`cfd_long` / `cfd_short` / `sgln_long` / `hold` / `idle` / `close` |
| `margin_pct` | 开仓时必填 | 保证金比例 0.0 - 1.0 |
| `tp` | CFD 必填 | 止盈价格（SGLN 设 0） |
| `sl` | CFD 必填 | 止损价格（SGLN 设 0） |
| `signal_strength` | 否 | 信号强度 0.0 - 1.0 |
| `signal_type` | 否 | 信号类型描述 |
| `reasoning` | 否 | 投资理由 |

**投资者 A**：CFD 1:20 杠杆，支持 `cfd_long` / `cfd_short` / `hold` / `idle` / `close`
**投资者 B**：SGLN 实物黄金 或 CFD 做空（互斥），支持 `sgln_long` / `cfd_short` / `hold` / `idle` / `close`

### 门铃（紧急通知）

当状态机进入 TRIGGER 或发生爆仓/止损/止盈时，GoldClaw POST 到 Bridge：

**Endpoint:** `POST /emergency`

```json
{
  "type": "emergency",
  "event": "state_trigger",
  "investor": "A",
  "gold_price": 4768.30,
  "priority": "urgent",
  "action_taken": "notifying_openclaw",
  "message": "TRIGGER: slope exceeded threshold, gold price $4768.30",
  "timestamp": "2026-04-09T21:56:58Z"
}
```

**event 类型：**

| 事件 | 说明 |
|------|------|
| `state_trigger` | 斜率触发 TRIGGER 状态，需要 OpenClaw 紧急决策 |
| `margin_call` | 爆仓（已自动平仓） |
| `stop_loss` | 触及止损（已自动平仓） |
| `take_profit` | 触及止盈（已自动平仓） |

### OpenClaw Cron Job 配置

OpenClaw 定期读取状态并做出投资决策。建议 cron 配置：

```bash
# 每 3 小时检查一次 GoldClaw 状态
0 */3 * * * openclaw agent --read ~/GoldClaw/data/state_for_openclaw.json --write ~/GoldClaw/data/orders_from_openclaw.json
```

**工作流程：**
1. OpenClaw cron 触发，读取 `~/GoldClaw/data/state_for_openclaw.json`
2. 分析市场状态、投资者持仓、风险指标
3. 生成投资决策，写入 `~/GoldClaw/data/orders_from_openclaw.json`
4. GoldClaw 下次 tick 自动读取并执行订单
5. 执行后文件归档为 `orders_processed_[timestamp].json`

**紧急流程：**
1. GoldClaw 检测到 TRIGGER/爆仓 → POST 到 Bridge URL
2. Bridge 触发 `openclaw agent --deliver -m "[紧急消息]"`
3. OpenClaw 即时响应，写入 `orders_from_openclaw.json`
4. GoldClaw 下次 tick（WATCH 态 3 分钟内）读取执行

### 通讯监控

所有通讯记录存储在 SQLite `comm_log` 表，Dashboard 可查看：

```sql
SELECT * FROM comm_log ORDER BY created_at DESC;

-- 字段：
-- direction:   "goldclaw→openclaw" | "openclaw→goldclaw"
-- event_type:  "tick" | "state_change" | "status_report" | "emergency" | "order"
-- payload:     JSON 详情
-- created_at:  ISO 8601 时间戳
```

---

## 状态机

```
IDLE ──(斜率 > THRESHOLD_A × 5次)──► WATCH ──(斜率 > THRESHOLD_B)──► TRIGGER
  ▲                                      │                              │
  └──────(冷却 30 分钟)────────────────────┘                              │
  └──────────────(TRIGGER 执行后回到 IDLE)─────────────────────────────────┘
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `CYCLE_X` | 5 | 连续触发次数进入 WATCH |
| `THRESHOLD_A` | 0.003 | IDLE 态斜率阈值 |
| `THRESHOLD_B` | 0.005 | WATCH 态斜率阈值 |
| `WATCH_DURATION` | 5 | WATCH 持续 tick 数 |
| `TRIGGER_SLOPE` | 0.002 | TRIGGER 斜率阈值 |
| `SILENCE_PERIOD` | 30 | 冷却期（分钟） |

以上参数可在 Dashboard「参数配置」中实时修改。

---

## 配置

编辑 `.env` 文件（源码模式）或 `~/GoldClaw/.env`（App 模式）：

```bash
# 金价 API
GOLD_API_URL=https://api.gold-api.com/price/XAU

# OpenClaw Bridge
OPENCLAW_BRIDGE_URL=http://localhost:8089/emergency
OPENCLAW_BRIDGE_TIMEOUT=30

# 数据库
DB_PATH=data/goldclaw.db

# 调度间隔（分钟）
SCHEDULE_INTERVAL_IDLE=15
SCHEDULE_INTERVAL_WATCH=3

# 初始资金
INITIAL_CASH_A=10000
INITIAL_CASH_B=10000
```

---

## 项目结构

```
GoldClaw/
├── app_main.py           # macOS App 入口（pywebview 原生窗口）
├── run.py                # CLI 入口（uvicorn + Engine）
├── dashboard_api.py      # FastAPI Dashboard API
├── openclaw_bridge.py    # OpenClaw Bridge 紧急通知服务
├── build_dmg.sh          # DMG 构建脚本
├── build.sh              # Tarball 构建脚本
├── config/               # 配置（pydantic-settings）
├── profiles/             # 投资者画像（YAML）
├── app/                  # 应用层（引擎 + 调度器）
├── internal/             # 业务逻辑
│   ├── price/            # 金价获取 + 波动率
│   ├── investor/         # 投资者模块 + 盈亏计算
│   ├── state_machine/    # 状态机（IDLE/WATCH/TRIGGER）
│   ├── exchange/         # 通信层（信箱 + 门铃 + Schema）
│   ├── db/               # SQLite 数据库 + 迁移
│   └── exception/        # 异常处理
├── dashboard/            # 前端（HTML + CSS + JS）
│   ├── index.html
│   └── static/
│       ├── style.css
│       ├── app.js
│       └── app_icon.icns
├── data/                 # 运行时数据（gitignored）
└── tests/                # 测试
```

---

## 技术栈

| 层 | 选型 |
|----|------|
| 语言 | Python 3.11+ |
| 数据库 | SQLite (WAL 模式) |
| Dashboard | FastAPI + Chart.js |
| 原生窗口 | pywebview (macOS WKWebView) |
| 调度 | APScheduler |
| HTTP | httpx |
| 校验 | Pydantic v2 |
| 配置 | pydantic-settings + .env |
| 打包 | PyInstaller + hdiutil (DMG) |

---

## 文档

| 文件 | 说明 |
|------|------|
| [PRD.md](PRD.md) | 产品需求文档 |
| [ARCH.md](ARCH.md) | 技术架构与工程约束 |
| [RULES.md](RULES.md) | OpenClaw 通信规范（JSON 格式、字段约束） |
| [project_state.md](project_state.md) | 项目当前状态 |

---

## License

Private project. All rights reserved.
