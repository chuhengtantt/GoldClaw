# project_state.md — GoldClaw 项目当前状态

> 本文档在任何时候打开，都能准确反映项目此刻的真实状态。
> 每次开新对话前让 AI 读这份文件，确保它的世界观是准的。

---

## 当前阶段

**切片 1-8 全部完成，核心引擎 v0.1 功能完整。** 120 个测试全绿（95 单元 + 25 集成）。
OpenClaw 端到端联调 23 步全部通过（2026-04-09）。Dashboard 开发中。

### 当前运行状态
- **GoldClaw**: 后台运行中（`nohup python main.py`）
- **Bridge**: 后台运行中（端口 8088）
- **OpenClaw**: cron 每 3 小时触发，已验证通路

---

## 已完成切片

### 切片 1: 数据库层 + 配置 ✅
### 切片 2: 金价获取 ✅
### 切片 3: 盈亏纯函数 + 测试（21 tests） ✅
### 切片 4: 投资者模块 + 数据库集成（55 tests） ✅
### 切片 5: 状态机（71 tests） ✅
### 切片 6: 通信层（95 tests） ✅
### 切片 7: 主引擎编排 ✅
- 验收通过：引擎启动、获取实时金价、写 state_for_openclaw.json、优雅关闭

### 切片 8: 集成测试 ✅
- 25 个集成测试，覆盖 10 个场景：
  - CFD 做多完整生命周期（开仓→盈利→TP→平仓）
  - CFD 做空完整生命周期（开仓→SL止损）
  - SGLN 完整生命周期（开仓→跟踪→指令平仓）
  - 爆仓紧急流程（margin_call → 自动平仓）
  - 投资者 B 仓位互斥切换（CFD↔SGLN）
  - 决策文件校验（合法/非法/混合/缺字段）
  - 状态报告生成（JSON 结构 + warnings）
  - 状态机联动（IDLE→WATCH→TRIGGER / 超时回退 / TP/SL触发）
  - 幻觉检测
  - 多 tick 端到端模拟（连续非法指令不崩溃）

---

## OpenClaw 接入指南

OpenClaw 开发者只需阅读 `RULES.md` 即可完成对接。以下是快速入门。

### 1. 数据文件位置

| 文件 | 方向 | 路径 |
|------|------|------|
| 状态文件 | GoldClaw → OpenClaw | `data/state_for_openclaw.json` |
| 决策文件 | OpenClaw → GoldClaw | `data/orders_from_openclaw.json` |
| SQLite 数据库 | 真相源 | `data/goldclaw.db`（OpenClaw 不碰） |

### 2. OpenClaw 需要做的事

**日常模式（cron 驱动）**：
1. 读取 `data/state_for_openclaw.json`，获取当前金价、投资者状态、系统状态
2. 根据状态做出投资决策
3. 写入 `data/orders_from_openclaw.json`，格式见 `RULES.md` 第 4 节
4. GoldClaw 下个 tick 自动捡起执行

**紧急模式（TRIGGER 门铃）**：
1. GoldClaw 检测到金价异常波动时，POST 到 `OPENCLAW_BRIDGE_URL`
2. Bridge（`openclaw_bridge.py`）收到请求后拉起 OpenClaw 会话
3. OpenClaw 读状态 → 紧急决策 → 写 `data/orders_from_openclaw.json`
4. GoldClaw 在 3 分钟内捡起执行

### 3. 决策文件格式（最简示例）

```json
{
  "timestamp": "2026-04-09T03:00:00Z",
  "instructions": [
    {
      "investor": "A",
      "action": "cfd_long",
      "margin_pct": 0.80,
      "tp": 4750.00,
      "sl": 4630.00,
      "reasoning": "降息预期"
    },
    {
      "investor": "B",
      "action": "idle"
    }
  ]
}
```

### 4. 权限速查

| Action | 投资者A | 投资者B |
|--------|---------|---------|
| `cfd_long` | ✅ | ❌ |
| `cfd_short` | ✅ | ✅ |
| `sgln_long` | ❌ | ✅ |
| `hold` | ✅ | ✅ |
| `idle` | ✅ | ✅ |
| `close` | ✅ | ✅ |

### 5. 校验规则（GoldClaw 自动执行）

- 格式校验：JSON 解析失败 → 拒收
- 权限校验：非法 action → 拦截 + 记录 violations
- margin_pct：开仓类必填，范围 0.0-1.0
- tp/sl：CFD 开仓必填（金价绝对价格），SGLN 填 0
- 幻觉检测：total_assets 变化 >50% → ROLLBACK
- 指令过期：timestamp 超 30 分钟 → 丢弃

---

## 数据库表速查

| 表 | 用途 | 操作 |
|----|------|------|
| `investor_state` | 两个投资者当前持仓状态 | 每 tick UPDATE |
| `trade_history` | 每笔开仓/平仓/止损/止盈记录 | INSERT Only |
| `system_state` | 状态机参数（状态、金价、波动率） | UPDATE |
| `violations` | OpenClaw 违规指令记录（耻辱柱） | INSERT Only |
| `price_ticks` | 金价 tick 历史（Dashboard 数据源） | INSERT Only |
| `comm_log` | 通讯日志（所有方向的事件记录） | INSERT Only |

---

## 待开发

- **Dashboard 前端**: `dashboard/` + `dashboard_api.py` 已搭建骨架，开发中
- **指令过期检测 (F5)**: PRD 中定义但未实现，当前不检查 timestamp TTL
- **门铃后轮询**: Bridge 触发后每 30s 检查 orders 文件（最多 3 分钟），未实现

## 运行配置

- **Bridge 端口**: 8088（端口 8000 被系统占用）
- **Bridge 启动**: `python openclaw_bridge.py`
- **引擎启动**: `python main.py`
- **测试**: `pytest tests/ -v`

```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动引擎
python main.py

# 运行测试
pytest tests/ -v

# 运行测试（含覆盖率）
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## 文件清单（已实现）

```
GoldClaw/
├── main.py                          # 入口
├── openclaw_bridge.py               # 门铃接收器（端口 8088）
├── dashboard_api.py                 # Dashboard REST API（FastAPI）
├── PRD.md                           # 产品需求
├── ARCH.md                          # 技术架构
├── RULES.md                         # OpenClaw 通信规范
├── OPENCLAW_ONBOARDING.md           # OpenClaw 接入联调清单（23步全完成）
├── project_state.md                 # 本文件
├── requirements.txt                 # 运行时依赖
├── requirements-dev.txt             # 开发依赖
├── .env / .env.example              # 环境配置
├── .gitignore
├── dashboard/                       # Dashboard 前端
│   ├── index.html
│   └── static/
├── docs/
│   └── dashboard_dev_plan.md        # Dashboard 开发计划
├── config/
│   ├── settings.py                  # pydantic-settings
│   └── defaults.py                  # 默认常量
├── profiles/
│   ├── investor_a.yaml
│   └── investor_b.yaml
├── app/
│   ├── engine.py                    # 主引擎（9步tick流水线）
│   └── scheduler.py                 # APScheduler 双频率调度
├── internal/
│   ├── state_machine/
│   │   ├── states.py                # SystemState + Action 枚举
│   │   └── machine.py               # 双重阈值 + 惯性确认
│   ├── price/
│   │   ├── fetcher.py               # API 客户端 + 重试
│   │   ├── history.py               # deque 滚动缓冲
│   │   └── volatility.py            # 斜率 + 波动率
│   ├── investor/
│   │   ├── pnl.py                   # 盈亏纯函数
│   │   ├── base.py                  # 抽象基类
│   │   ├── investor_a.py            # 投资者A
│   │   └── investor_b.py            # 投资者B
│   ├── db/
│   │   ├── connection.py            # SQLite WAL
│   │   ├── migrations.py            # 建表 + 初始数据
│   │   └── repository.py            # InvestorRepository + DashboardRepository
│   ├── exchange/
│   │   ├── schema.py                # Pydantic Schema
│   │   ├── webhook_client.py        # 信箱读写 + 门铃 POST
│   │   └── validator.py             # 校验 + 幻觉检测 + 耻辱柱
│   └── exception/
│       ├── errors.py                # 自定义异常
│       └── handler.py               # 错误处理器
├── data/                            # 运行时数据（gitignored）
│   ├── goldclaw.db
│   ├── state_for_openclaw.json
│   └── orders_from_openclaw.json
└── tests/
    ├── test_pnl_calculations.py     # 21 tests
    ├── test_state_machine.py        # 16 tests
    ├── test_schema_validation.py    # 24 tests
    ├── test_investor_a.py           # 20 tests
    ├── test_investor_b.py           # 14 tests
    └── test_integration.py          # 25 tests (切片 8)
```

---

## 已知问题

- **F5 指令过期检测未实现**: PRD 定义了 30 分钟 TTL，但代码未检查 timestamp。当前所有指令都会被执行（不影响安全，因为 Pydantic 校验仍在）。
- **15 分钟延迟**: OpenClaw 写入 orders 文件后，GoldClaw 最长需要等 15 分钟（IDLE tick 间隔）才捡起执行。
