# GoldClaw 🦞

> 量化黄金交易模拟引擎 — Quantitative Gold Trading Simulation Engine

---

## 中文

### 这是什么？

GoldClaw 是一个本地运行的 Python 定时引擎，用于模拟黄金（XAU）交易。它通过实时金价 API 监控市场，接收外部 LLM 系统（OpenClaw）的投资指令，自动执行模拟交易的资产计算、止损止盈监控和爆仓检测。

### 核心特性

- **实时金价监控**：每 15 分钟（IDLE）/ 3 分钟（WATCH）获取金价，支持 API 重试和缓存兜底
- **双投资者模型**：
  - 投资者 A — CFD 1:20 趋势收割者（做多/做空）
  - 投资者 B — SGLN 防御性狙击手（CFD 做空 或 SGLN 做多，互斥）
- **三态状态机**：IDLE → WATCH → TRIGGER，带惯性确认和冷却期
- **信箱 + 门铃通信**：与 OpenClaw 通过 JSON 文件交换数据，紧急时 HTTP POST 唤醒
- **多层安全防护**：SQLite ACID 事务 + Pydantic 校验 + 幻觉检测 + 耻辱柱
- **自动化风控**：止损/止盈/爆仓自动平仓，无需人工干预

### 快速开始

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/GoldClaw.git
cd GoldClaw

# 2. 创建虚拟环境
python3.13 -m venv .venv
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的配置

# 5. 启动引擎
python main.py

# 6. 运行测试
pytest tests/ -v
```

### 项目结构

```
GoldClaw/
├── main.py              # 入口
├── config/              # 配置（pydantic-settings）
├── profiles/            # 投资者画像（YAML）
├── app/                 # 应用层（引擎 + 调度器）
├── internal/            # 业务逻辑
│   ├── price/           # 金价获取 + 波动率
│   ├── investor/        # 投资者模块 + 盈亏计算
│   ├── state_machine/   # 状态机（IDLE/WATCH/TRIGGER）
│   ├── exchange/        # 通信层（信箱 + 门铃）
│   ├── db/              # SQLite 数据库
│   └── exception/       # 异常处理
├── data/                # 运行时数据（gitignored）
└── tests/               # 测试（95 tests）
```

### 文档

| 文件 | 说明 |
|------|------|
| [PRD.md](PRD.md) | 产品需求文档 |
| [ARCH.md](ARCH.md) | 技术架构与工程约束 |
| [RULES.md](RULES.md) | OpenClaw 通信规范（JSON 格式、字段约束） |
| [project_state.md](project_state.md) | 项目当前状态 |

### 技术栈

| 层 | 选型 |
|----|------|
| 语言 | Python 3.11+ |
| 数据库 | SQLite (WAL 模式) |
| 调度 | APScheduler |
| HTTP 客户端 | httpx |
| 数据校验 | Pydantic v2 |
| 配置 | pydantic-settings + .env |

---

## English

### What is this?

GoldClaw is a locally-run Python scheduled engine for simulating gold (XAU) trading. It monitors the market via a real-time gold price API, receives investment instructions from an external LLM system (OpenClaw), and automatically executes simulated trade calculations including PnL tracking, stop-loss/take-profit monitoring, and margin call detection.

### Key Features

- **Real-time Gold Price Monitoring**: Fetches prices every 15min (IDLE) / 3min (WATCH), with API retries and cache fallback
- **Dual Investor Model**:
  - Investor A — CFD 1:20 Trend Reaper (long/short)
  - Investor B — SGLN Defensive Sniper (CFD short OR SGLN long, mutually exclusive)
- **Three-State Machine**: IDLE → WATCH → TRIGGER with inertia confirmation and cooldown period
- **Mailbox + Doorbell Communication**: JSON file exchange with OpenClaw, HTTP POST for urgent wake-up
- **Multi-layer Security**: SQLite ACID transactions + Pydantic validation + hallucination detection + violations log
- **Automated Risk Control**: Auto-close on stop-loss / take-profit / margin call without manual intervention

### Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/your-username/GoldClaw.git
cd GoldClaw

# 2. Create virtual environment
python3.13 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your settings

# 5. Start the engine
python main.py

# 6. Run tests
pytest tests/ -v
```

### Project Structure

```
GoldClaw/
├── main.py              # Entry point
├── config/              # Configuration (pydantic-settings)
├── profiles/            # Investor profiles (YAML)
├── app/                 # Application layer (engine + scheduler)
├── internal/            # Business logic
│   ├── price/           # Gold price fetching + volatility
│   ├── investor/        # Investor modules + PnL calculation
│   ├── state_machine/   # State machine (IDLE/WATCH/TRIGGER)
│   ├── exchange/        # Communication (mailbox + doorbell)
│   ├── db/              # SQLite database
│   └── exception/       # Exception handling
├── data/                # Runtime data (gitignored)
└── tests/               # Tests (95 tests)
```

### Documentation

| File | Description |
|------|-------------|
| [PRD.md](PRD.md) | Product requirements |
| [ARCH.md](ARCH.md) | Technical architecture & engineering constraints |
| [RULES.md](RULES.md) | OpenClaw communication spec (JSON format, field constraints) |
| [project_state.md](project_state.md) | Current project status |

### Tech Stack

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ |
| Database | SQLite (WAL mode) |
| Scheduling | APScheduler |
| HTTP Client | httpx |
| Validation | Pydantic v2 |
| Config | pydantic-settings + .env |

---

## License

Private project. All rights reserved.
