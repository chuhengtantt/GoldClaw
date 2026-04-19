# GoldClaw PRD — 量化黄金交易模拟引擎

> 版本: v0.4.0 | 日期: 2026-04-15 | 状态: Released

---

## 1. 产品概述

### 一句话定义

GoldClaw 是一个本地运行的 Python 定时引擎，通过实时金价 API 监控黄金市场，根据外部 LLM 系统（OpenClaw）通过 Webhook 传来的投资指令，自动执行模拟交易的资产计算、止损止盈监控和爆仓检测。所有状态由 SQLite 数据库管理，Python 引擎是唯一的数据库管理员。

### 解决什么问题

- 将 LLM 的投资决策（JSON）转化为可执行的模拟交易动作
- 自动化繁琐的资产计算（杠杆盈亏、费用扣除、隔夜利息）
- 7×24 小时无人值守监控，在金价异常波动时自主平仓保命
- SQLite 存储提供"防弹级"数据安全，LLM 误写不会破坏底层数据

### 本地运行

- macOS .app 应用（DMG 安装），双击启动，原生窗口 Dashboard
- 也可通过 `python run.py` 命令行启动（开发模式）
- 所有数据存储在本地 SQLite 单文件中
- 打包后数据目录：`~/GoldClaw/data/`（方便 OpenClaw 访问）
- 与外部 AI 系统通过 JSON 文件 + HTTP POST 通信

---

## 2. 系统架构

### 2.1 架构范围（仅 Python Engine）

GoldClaw 只负责 Python Engine 侧的开发。OpenClaw 是外部的 LLM 系统，不在本项目的开发范围内。

```
                          外部系统（不在本项目范围内）
                         ┌────────────────────────┐
                         │       OpenClaw (LLM)    │
                         │  cron 定时 / 门铃唤醒    │
                         │  读信箱 → 写决策文件     │
                         └──────────▲───▲───────────┘
                                    │   │
                       信箱 JSON 文件│   │信箱 JSON 文件
                       (状态覆写)    │   │(投资决策)
                                    │   │
┌───────────────────────────────────┼───┼────────────────────┐
│                     GoldClaw Python Engine                  │
│                          (本项目范围)                        │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐  ┌──────────┐ │
│  │  金价获取 │──►│  状态机  │──►│ 资产计算  │──►│ SQLite   │ │
│  │  (input) │   │IDLE/WATCH│   │  引擎     │  │ (存储)   │ │
│  │  15/3min │   │ /TRIGGER │   │           │  │          │ │
│  └──────────┘   └──────────┘   └──────────┘  └──────────┘ │
│       ▲                          │                    ▲     │
│       │ HTTP GET                 │ 信箱覆写           │     │
│  ┌────┴─────┐                    ▼                    │     │
│  │ Gold API │             ┌────────────┐    ┌────────┴──┐  │
│  └──────────┘             │  校验层    │    │  trade_    │  │
│                           │ (Pydantic) │    │  history   │  │
│                           │ 拒收非法指令│    │  (只增不改) │  │
│                           └────────────┘    └───────────-┘  │
│                                                             │
│  门铃（TRIGGER 时）: POST → OPENCLAW_BRIDGE_URL             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 通信闭环（信箱 + 门铃 混合模式）

OpenClaw 是 cron 驱动的孤立会话，不是 HTTP 服务器。因此采用"信箱 + 门铃"混合通信模式。

**铁律**：OpenClaw 永远不直接碰数据库。Python 引擎是唯一的"数据库管理员（DBA）"。

#### 信箱模式（日常运作）

Python 每 tick 将状态从 SQLite 提取，单向覆写到文件。OpenClaw 在 cron 唤醒时读取。

**发信（Python → OpenClaw）**：
1. Python 查询 SQLite：`SELECT * FROM investor_state`
2. Python 组装精简 JSON，覆写 `data/state_for_openclaw.json`
3. OpenClaw cron 唤醒时读取此文件

**收信与校验（OpenClaw → Python）**：
1. OpenClaw 思考后写入 `data/orders_from_openclaw.json`
2. Python 下一个 tick 检测到文件存在
3. Python 执行 Pydantic 严格校验
4. 校验失败 → 拒收，记录 violations，数据库毫发无损
5. 校验成功 → 执行交易，写入 SQLite
6. 处理完毕后重命名为 `data/orders_processed_[timestamp].json`，防止重复读取

#### 门铃模式（紧急触发）

当 Python 检测到金价异常波动（TRIGGER），需要立刻叫醒 OpenClaw 执行投资角色。主动权在 GoldClaw。

**流程**：
1. Python 触发 TRIGGER（趋势确认 / 止损 / 止盈 / 爆仓）
2. Python 先执行自主操作（自动平仓等）
3. Python 写信箱 `state_for_openclaw.json`（含触发原因）
4. Python POST 到 `OPENCLAW_BRIDGE_URL`（本地 HTTP Bridge）
5. Bridge 收到请求，强制拉起一次 OpenClaw 会话
6. OpenClaw 读状态 → 紧急决策 → 写 `orders_from_openclaw.json`
7. Python 下个 tick（3 分钟内）捡起决策执行

**Bridge 说明**：
- `openclaw_bridge.py` 是 OpenClaw 侧的极简 FastAPI 脚本，不在本项目开发范围内
- Python 只需支持 POST 到配置的 URL 即可
- URL 未配置时，退化为纯信箱模式（等 OpenClaw 下次 cron）

**紧急事件**：
- 止损/爆仓/止盈 → Python 自主平仓 → 按门铃通知 OpenClaw
- OpenClaw 无需响应，纯通知性质

### 2.3 数据流

```
Input:
  1. 金价 API (每 15/3 分钟主动请求) → 实时金价
  2. data/orders_from_openclaw.json (OpenClaw cron 写入) → 投资决策 JSON

Output:
  1. SQLite (goldclaw.db) → 所有状态和历史（真相源）
  2. data/state_for_openclaw.json (每 tick 覆写) → OpenClaw 读取的状态
  3. POST to Bridge URL (TRIGGER 时) → 紧急唤醒 OpenClaw
  4. trade_history 表 (INSERT Only) → 交易流水，未来社媒素材库
```

### 2.4 金价 API

- **Endpoint**: `https://api.gold-api.com/price/XAU`
- **方式**: HTTP GET
- **响应**: JSON，包含当前 XAU 金价（美元/盎司）
- **超时**: 10 秒
- **重试**: 3 次指数退避

### 2.5 与 OpenClaw 的接口约定

OpenClaw 是外部 LLM 系统，不在本项目开发范围内。双方的接口约定如下：

- **通信方式**: 信箱（JSON 文件交换）+ 门铃（可选 HTTP POST 唤醒）
- **Python → OpenClaw**: 每 tick 覆写 `data/state_for_openclaw.json`
- **OpenClaw → Python**: 写入 `data/orders_from_openclaw.json`，Python 下个 tick 读取
- **紧急唤醒**: TRIGGER 时 POST 到 `OPENCLAW_BRIDGE_URL`（可选，未配置则退化为纯信箱）
- **JSON 格式**: 见第 7 节 Payload 定义
- **数据安全**: OpenClaw 无法直接操作 SQLite，所有写入必须经过 Python 校验层

---

## 3. 功能列表

### 3.1 必须有 (Must Have)

| # | 功能 | 说明 |
|---|------|------|
| F1 | 金价获取 | 每 15/3 分钟从 API 获取实时金价，存入价格历史 |
| F2 | 状态机 | IDLE(15min) → WATCH(3min) → TRIGGER(即时)，惯性确认机制 + Webhook 冷却期 |
| F3 | 接收交易指令 | 通过 Webhook Response 接收 OpenClaw 的投资决策 |
| F4 | 指令校验 | Pydantic 严格校验 + 幻觉检测，非法格式拦截 |
| F5 | 指令过期检测 | 超过 30 分钟的指令自动丢弃 |
| F6 | 开仓执行 | 根据指令建立 CFD/SGLN 仓位，扣除 Spread |
| F7 | 平仓执行 | 计算净盈亏，扣除 FX 费 + 隔夜利息 |
| F8 | 持仓盈亏计算 | 每 tick 计算名义盈亏和净盈亏 |
| F9 | 止损监控 | 触及止损价格自动平仓 |
| F10 | 止盈监控 | 触及止盈价格自动平仓 |
| F11 | 爆仓检测 | 保证金归零时自动平仓 |
| F12 | 状态持久化 | 每 tick 更新 SQLite 数据库 |
| F13 | Webhook 通知 | 爆仓/止损/止盈时发送 HTTP POST 到 OpenClaw |
| F14 | 数据库安全 | SQLite ACID 事务 + WAL 模式，防止数据损坏 |
| F15 | LLM 误写隔离 | OpenClaw 永远无法直接操作 SQLite |
| F16 | 优雅启动/关闭 | Ctrl+C 时完成当前 tick 后退出 |
| F17 | 日志记录 | 所有关键操作写入 trade_history 表 |
| F18 | 幻觉检测 | 交易前后数值变化超阈值则忽略并记录耻辱柱 |

### 3.2 将来再说 (Nice to Have)

| # | 功能 | 说明 |
|---|------|------|
| F19 | ~~前端可视化 Dashboard~~ | ✅ v0.2.0 已完成（Revolut 风格，Chart.js 折线图，两页 Tab） |
| F20 | ~~前后端接口规范~~ | ✅ v0.2.0 已完成（FastAPI REST API，/api/* 端点） |
| F21 | 自动化社媒运营 | 自动生成交易摘要、盈亏截图、投资故事，发布到社交平台 |
| F22 | 社媒内容模板 | 可编辑的社媒发布模板（包含投资者表现、金评、每日/周报） |
| F23 | 历史回测 | 导入历史金价数据进行策略回测 |
| F24 | Telegram/Discord 通知 | 除 Webhook 外的即时通讯通知 |
| F25 | 多币种支持 | 除 XAU 外支持白银、原油等 |
| F26 | ~~投资者画像热更新~~ | ✅ v0.2.0 已完成（Dashboard 参数配置 + runtime_config 表） |
| F27 | 交易报告生成 | 定期生成 PDF/HTML 交易报告 |
| F28 | ~~数据库备份系统~~ | ✅ v0.4.0 已完成（自动启动/关闭备份 + 手动 Dashboard 备份 + 滚动保留 10 份） |
| F29 | ~~中英文语言切换~~ | ✅ v0.4.0 已完成（Dashboard 中/英文一键切换，localStorage 持久化） |
| F30 | ~~投资者资产曲线~~ | ✅ v0.4.0 已完成（A/B 双线折线图 + 决策标注 + 每 tick 快照） |

> **前后端分离**: v0.2.0 已实现。Dashboard 前端（HTML/CSS/JS）通过 FastAPI REST API（`/api/*`）获取数据。引擎核心逻辑（盈亏计算、状态机）与 Dashboard 解耦，通过 `DashboardRepository` 数据访问层桥接。
>
> **v0.4.0 新增**: 数据库备份系统（自动启动/关闭 + 手动 Dashboard）、中英文语言切换、投资者 A/B 资产曲线图（仅展示决策点 + 标注）、每 tick 资产快照后台记录。

---

## 4. 用户流程

### 4.1 完整运行流程（从启动到持续运行）

```
用户操作                              系统行为
────────                              ─────────
1. 用户打开终端
   运行 python main.py         →    引擎启动
                                    ├─ 检查/创建 data/ 目录
                                    ├─ 初始化 SQLite 数据库（如不存在）
                                    ├─ 加载 .env 配置
                                    ├─ 恢复状态机（从 system_state 表）
                                    ├─ 启动 APScheduler
                                    └─ 打印 "GoldClaw started, state=IDLE"

2. 引擎自动运行（无需用户操作）
                                    每 15 分钟 (IDLE) / 3 分钟 (WATCH):
                                    ├─ GET https://api.gold-api.com/price/XAU
                                    ├─ 记录金价到价格历史
                                    ├─ 计算波动率 & 斜率
                                    ├─ 更新状态机 (IDLE/WATCH/TRIGGER)
                                    ├─ 计算所有投资者盈亏
                                    ├─ UPDATE investor_state 表
                                    ├─ 检查止盈/止损/爆仓
                                    │   ├─ 触发 → 自动平仓 → 门铃通知
                                    │   └─ 未触发 → 继续
                                    ├─ 检查 orders_from_openclaw.json
                                    │   ├─ 有新决策 → Pydantic 校验 → 执行
                                    │   └─ 无决策 → 继续
                                    ├─ 覆写 state_for_openclaw.json
                                    └─ COMMIT 事务

3. 每 3 小时（OpenClaw cron 唤醒时）
     OpenClaw（不在本项目范围）:
                                    ├─ 读取 state_for_openclaw.json
                                    ├─ 做出投资决策
                                    └─ 写入 orders_from_openclaw.json
     GoldClaw 下个 tick:
                                    ├─ 读取 orders_from_openclaw.json
                                    ├─ Pydantic 校验 + 幻觉检测
                                    │   ├─ 合法 → UPDATE SQLite
                                    │   └─ 非法 → INSERT violations + 延续当前策略
                                    └─ 重命名已处理的决策文件

4. 用户按 Ctrl+C             →    引擎优雅关闭
                                    ├─ 完成当前 tick + COMMIT
                                    └─ 打印 "GoldClaw stopped"
```

### 4.2 首次运行流程

```
1. 用户配置 .env 文件（初始资金、Webhook URL 等）
2. 运行 python main.py
3. 引擎检测到无数据库文件
   ├─ 创建 data/goldclaw.db
   ├─ 执行建表 SQL（investor_state, trade_history, system_state, violations）
   ├─ 初始化投资者 A/B 数据（INSERT）
   └─ 获取第一笔金价
4. 引擎进入 IDLE 状态，开始每 15 分钟轮询
5. 首个 3 小时周期 Webhook 推送状态给 OpenClaw，等待首次投资决策
```

### 4.3 爆仓紧急流程

```
1. 引擎在某个 tick 检测到投资者 A 的保证金归零
2. 引擎立即自动平仓（不等 OpenClaw）
3. 重新计算投资者 A 的余额
   ├─ 剩余现金 = max(0, cash + net_pnl)
   └─ margin_call = 1
4. UPDATE investor_state（SQLite 事务）
5. INSERT trade_history（记录平仓流水）
6. 发送 Webhook POST 紧急通知到 OpenClaw
   ├─ 成功 → 记录日志 "Webhook sent: margin_call A"
   └─ 失败/超时 → 记录错误日志，继续运行
7. 继续进入下一个 tick
```

---

## 5. 投资者模型

### 5.1 投资者 A — CFD 1:20 趋势收割者

- **工具**: CFD 做多或做空
- **杠杆**: 20x
- **仓位**: 同一时间最多 1 个 CFD 仓位
- **费率**:

| 费用 | 公式 | 时机 |
|------|------|------|
| Spread | `margin × 1%` | 开仓扣除 |
| 隔夜利息 | `margin × 0.82% × nights_held` | 持仓期间累计 |
| FX 转换费 | `abs(名义盈亏) × 0.5%` | 平仓扣除 |

- **盈亏**:

```
actual_margin    = margin - spread
nominal_exposure = actual_margin × 20
nominal_pnl      = nominal_exposure × (current_price - entry_price) / entry_price
net_pnl          = nominal_pnl - abs(nominal_pnl) × 0.005 - overnight_interest
total_assets     = cash + actual_margin + nominal_pnl    (持仓期间)
```

### 5.2 投资者 B — SGLN 防御性狙击手

- **工具**: CFD 做空或 SGLN 做多（二选一，不同时持仓）
- **杠杆**: CFD 20x，SGLN 无杠杆
- **仓位**: 同一时间只有 1 个仓位（CFD 空头 **或** SGLN 多头，互斥）
- **CFD 做空费率**: 同投资者 A（Spread 1%、隔夜 0.82%、FX 0.5%）
- **SGLN 费率**: 无交易成本，无止盈线，无止损线
- **SGLN 盈亏**: 直接等于金价涨跌百分比 × 投入金额

- **CFD 做空盈亏**:

```
actual_margin    = margin - spread
nominal_exposure = actual_margin × 20
nominal_pnl      = nominal_exposure × (entry_price - current_price) / entry_price   ← 做空方向相反
net_pnl          = nominal_pnl - abs(nominal_pnl) × 0.005 - overnight_interest
```

- **SGLN 做多盈亏**:

```
pnl = investment × (current_gold_price / entry_gold_price - 1)
```

> 注意：SGLN 不设 TP/SL，PnL 直接跟踪金价涨跌百分比。SGLN 仓位仅通过 OpenClaw 发出 `close` 指令平仓。

- **投资者 B 总资产**:

```
if cfd持仓:  total_assets = cash + cfd_actual_margin + cfd_nominal_pnl
if sgln持仓: total_assets = cash + sgln_investment + sgln_pnl
if 空仓:     total_assets = cash
```

> **铁律**: 持仓未平期间，actual_margin 必须计入总资产。绝对禁止只拿 cash + 浮亏作为总资产。

---

## 6. 状态机

状态机的核心设计思想是"惯性确认"：通过监控窗口与状态切换的时间点对齐，过滤掉瞬时的、无意义的随机波动（Noise），确保 OpenClaw 只在真正的趋势形成或加速时才介入。

### 6.1 三态模型

```
┌──────────────────────────────────────────────────────────┐
│                  IDLE (常态巡航 · 每 15 分钟)              │
│  目标：识别"变盘的苗头"                                    │
│  监控：CYCLE_X 窗口内累积斜率 & 斜率差值突变               │
│  条件满足 → 切换至 WATCH，重置计时器和参考金价              │
└────────────────────────┬─────────────────────────────────┘
                         │ Total_Slope > THRESHOLD_A
                         │ 或 abs(Slope_Delta) > THRESHOLD_B
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  WATCH (高频盯盘 · 每 3 分钟)              │
│  目标：确认"波动是否具有持续性"                             │
│  从进入 WATCH 的时刻起重新计算斜率                          │
│  条件满足 → 切换至 TRIGGER                                │
│  超时未触发 → 退回 IDLE                                   │
└────────────────────────┬─────────────────────────────────┘
                         │ Slope_Since_Watch_Start > THRESHOLD_TRIGGER_SLOPE
                         │ 或触及止损/止盈/爆仓
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  TRIGGER (即时执行)                        │
│  动作：自动平仓 / 发送 Webhook → 进入 SILENCE_PERIOD       │
│  冷却结束后 → 回到 IDLE                                   │
└──────────────────────────────────────────────────────────┘
```

### 6.2 可配置参数（环境变量）

| 参数名 | 环境变量 | 默认值 | 说明 |
|--------|----------|--------|------|
| CYCLE_X | `GOLDCLAW_CYCLE_X` | 15 (分钟) | IDLE 阶段计算窗口长度 |
| THRESHOLD_A | `GOLDCLAW_THRESHOLD_A` | 0.0015 (0.15%) | 累积斜率阈值：整个 CYCLE_X 窗口内的总涨跌幅斜率 |
| THRESHOLD_B | `GOLDCLAW_THRESHOLD_B` | 0.001 (0.1%) | 斜率差阈值：当前短周期斜率与上一周期斜率的差值绝对值 |
| WATCH_DURATION | `GOLDCLAW_WATCH_DURATION` | 30 (分钟) | WATCH 阶段最长观察期 |
| THRESHOLD_TRIGGER_SLOPE | `GOLDCLAW_TRIGGER_SLOPE` | 0.001 (0.1%) | WATCH 期间允许的最大斜率阈值 |
| SILENCE_PERIOD | `GOLDCLAW_SILENCE_PERIOD` | 15 (分钟) | Webhook 发送后的强制冷却期 |

### 6.3 阶段一：IDLE (常态巡航)

**目标**：识别"变盘的苗头"。

**监控参数**：
- **CYCLE_X**：计算窗口长度（默认 15 分钟）
- **THRESHOLD_A**：整个窗口内的总涨跌幅斜率（累积斜率）
- **THRESHOLD_B**：斜率差 — 当前短周期斜率与上一周期斜率的差值绝对值（捕捉突发变向）

**判定逻辑**：

```
Total_Slope = (当前金价 - 窗口起始金价) / 窗口起始金价
Current_Slope = 最近一个短周期（3 分钟）的斜率
Prev_Slope = 上一个短周期的斜率
Slope_Delta = abs(Current_Slope - Prev_Slope)

if Total_Slope(Cycle_X) > THRESHOLD_A:
    → 切换至 WATCH
    → 重置内部计时器和参考金价

elif Slope_Delta > THRESHOLD_B:
    → 切换至 WATCH
    → 重置内部计时器和参考金价
```

**为什么两个阈值**：
- THRESHOLD_A 捕捉"持续性的温和趋势"（金价一直在缓慢但稳定地涨）
- THRESHOLD_B 捕捉"突发性的方向改变"（金价突然加速或反转）
- 两者任一满足即进入 WATCH，形成双重预警

### 6.4 阶段二：WATCH (高频盯盘)

**目标**：确认"波动是否具有持续性"。

**监控参数**：
- **WATCH_DURATION**：WATCH 阶段最长观察期（默认 30 分钟）
- **THRESHOLD_TRIGGER_SLOPE**：WATCH 期间允许的最大斜率阈值（默认 0.1%）

**判定逻辑**：

```
从进入 WATCH 的那一刻起，重新以进入时刻的金价为基准计算斜率。
Slope_Since_Watch_Start = (当前金价 - WATCH起始金价) / WATCH起始金价

if Slope_Since_Watch_Start > THRESHOLD_TRIGGER_SLOPE:
    → 切换至 TRIGGER，发送 Webhook

elif 触及止损/止盈线:
    → 切换至 TRIGGER

elif 检测到爆仓:
    → 切换至 TRIGGER（紧急）

elif 已在 WATCH 超过 WATCH_DURATION 且斜率未突破:
    → 退回 IDLE（波动是噪音，不具有持续性）
```

**退回 IDLE 的条件**：
- 斜率未突破阈值 + 波动率回落 + 超过 WATCH_DURATION
- 三个条件同时满足才退回，避免过早放弃监控

### 6.5 阶段三：TRIGGER (即时执行)

**动作**：
1. 根据触发原因执行对应操作（自动平仓 / 止损 / 止盈 / 爆仓平仓）
2. 发送 Webhook 通知 OpenClaw
3. 强制进入 **SILENCE_PERIOD**（冷却期）

### 6.6 Webhook 冷却机制 (SILENCE_PERIOD)

**问题**：如果斜率一直很大，Python 会在下一个 3 分钟循环里因为斜率依然很高而再次报警，导致 OpenClaw 收到大量重复通知。

**解决方案**：Webhook 发送后（无论成功与否），强制进入 SILENCE_PERIOD。

```
发送 Webhook 后:
  silence_until = now + SILENCE_PERIOD

每次检查是否触发 Webhook 前:
  if now < silence_until:
      → 跳过 Webhook 发送
      → 正常执行引擎其他逻辑（盈亏计算、JSON 写入等）
  else:
      → 恢复正常的 Webhook 触发逻辑
```

- **默认冷却期**: 15 分钟
- **冷却期间**: Webhook 不发送，但引擎的其他功能（盈亏计算、止损止盈、JSON 写入）正常运行
- **止损/爆仓不受冷却限制**: 如果是止损或爆仓触发的紧急事件，无视冷却期，立即发送 Webhook

### 6.7 状态持久化

当前状态及参数持久化到 SQLite `system_state` 表，程序重启后可恢复。每 tick UPDATE。

---

## 7. 数据存储与接口

### 7.1 SQLite 数据库（goldclaw.db）

所有数据存储在本地 SQLite 单文件 `data/goldclaw.db` 中。Python 引擎是唯一的数据库管理员。

#### 表 1: investor_state（投资者当前状态）

记录每个投资者最新的资产和仓位状态。每个投资者一行，随时被 `UPDATE` 更新。

```sql
CREATE TABLE investor_state (
    investor_id       TEXT PRIMARY KEY,           -- "A", "B"（未来可扩展 "C", "D", ...）
    total_assets      REAL NOT NULL DEFAULT 0,    -- 总资产 = cash + margin_committed + nominal_pnl
    cash              REAL NOT NULL DEFAULT 0,    -- 可用现金
    margin_committed  REAL NOT NULL DEFAULT 0,    -- 已投入保证金（空仓时为 0）
    current_action    TEXT NOT NULL DEFAULT 'idle', -- 当前持仓: cfd_long, cfd_short, sgln_long, hold, idle
    entry_price       REAL,                       -- 开仓金价（空仓时 NULL）
    current_price     REAL NOT NULL DEFAULT 0,    -- 最近一次金价
    tp                REAL DEFAULT 0,             -- 止盈价格（金价绝对价格，SGLN 时为 0）
    sl                REAL DEFAULT 0,             -- 止损价格（金价绝对价格，SGLN 时为 0）
    nominal_pnl       REAL NOT NULL DEFAULT 0,    -- 名义盈亏
    net_pnl           REAL NOT NULL DEFAULT 0,    -- 净盈亏（扣费后）
    overnight_interest_accrued REAL NOT NULL DEFAULT 0, -- 累计隔夜利息
    nights_held       INTEGER NOT NULL DEFAULT 0, -- 持仓天数
    margin_call       INTEGER NOT NULL DEFAULT 0, -- 0=正常, 1=已爆仓
    pnl_pct           REAL NOT NULL DEFAULT 0,    -- 收益率
    entry_timestamp   TEXT,                       -- 开仓时间（ISO 8601）
    initial_cash      REAL NOT NULL DEFAULT 10000, -- 初始资金（用于计算总收益率）
    updated_at        TEXT NOT NULL               -- 最后更新时间
);
```

**初始化数据**：

```sql
INSERT INTO investor_state (investor_id, total_assets, cash, initial_cash, current_action, updated_at)
VALUES ('A', 10000.00, 10000.00, 10000.00, 'idle', datetime('now'));

INSERT INTO investor_state (investor_id, total_assets, cash, initial_cash, current_action, updated_at)
VALUES ('B', 10000.00, 10000.00, 10000.00, 'idle', datetime('now'));
```

#### 表 2: trade_history（交易流水 — 只增不改）

记录每一次建仓、平仓、爆仓及触发原因。是未来回测复盘和社媒素材的数据源。

```sql
CREATE TABLE trade_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,                -- 交易时间（ISO 8601）
    investor_id     TEXT NOT NULL,                -- "A" 或 "B"
    action          TEXT NOT NULL,                -- cfd_long, cfd_short, sgln_long, close, margin_call, stop_loss, take_profit
    gold_price      REAL NOT NULL,                -- 交易时的金价
    entry_price     REAL,                         -- 开仓价（平仓时为该笔仓位的开仓价）
    exit_price      REAL,                         -- 平仓价（开仓时为 NULL）
    margin_committed REAL,                        -- 本次投入保证金
    nominal_pnl     REAL,                         -- 名义盈亏
    net_pnl         REAL,                         -- 净盈亏（扣费后）
    fees_total      REAL,                         -- 本次总费用（spread + fx + overnight）
    cash_after      REAL NOT NULL,                -- 交易后现金余额
    total_assets_after REAL NOT NULL,             -- 交易后总资产
    trigger_reason  TEXT,                         -- 触发原因: manual, sl_hit, tp_hit, margin_call, signal_reversal, state_trigger
    signal_strength REAL,                         -- 信号强度（仅记录）
    signal_type     TEXT,                         -- 信号类型（仅记录）
    reasoning       TEXT                          -- 决策理由（仅记录）
);
```

#### 表 3: system_state（系统状态）

记录状态机和全局参数。只有一行。

```sql
CREATE TABLE system_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1), -- 只有一行
    state           TEXT NOT NULL DEFAULT 'IDLE',  -- IDLE, WATCH, TRIGGER
    gold_price      REAL NOT NULL DEFAULT 0,
    price_source    TEXT DEFAULT '',
    volatility      REAL NOT NULL DEFAULT 0,
    slope_3min      REAL NOT NULL DEFAULT 0,
    entered_at      TEXT,                           -- 进入当前状态的时间
    watch_start_price REAL,                         -- 进入 WATCH 时的金价
    watch_start_time TEXT,                          -- 进入 WATCH 的时间
    silence_until   TEXT,                           -- Webhook 冷却截止时间
    prev_slope      REAL DEFAULT 0,                 -- 上一个短周期斜率
    last_tick       TEXT NOT NULL,                  -- 最后一次 tick 时间
    last_price_update TEXT                          -- 最后金价更新时间
);
```

#### 表 4: violations（耻辱柱 — 非法指令记录）

记录 OpenClaw 的每一次违规操作。只增不改。

```sql
CREATE TABLE violations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL,
    investor_id     TEXT NOT NULL,
    violation       TEXT NOT NULL,                  -- 违规描述
    original_action TEXT NOT NULL,                  -- OpenClaw 尝试的动作
    action_taken    TEXT NOT NULL,                  -- Python 实际执行的动作（通常为 "blocked, continued xxx"）
    acknowledged    INTEGER DEFAULT 0               -- 0=未通报, 1=已通过 Webhook 通报给 OpenClaw
);
```

#### 表 5: price_ticks（金价 tick 历史）

每次 tick 记录金价、波动率、斜率。Dashboard 数据源。

```sql
CREATE TABLE price_ticks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    price      REAL NOT NULL,
    source     TEXT DEFAULT '',
    tick_time  TEXT NOT NULL,
    volatility REAL DEFAULT 0,
    slope      REAL DEFAULT 0
);
```

#### 表 6: comm_log（通讯日志）

记录所有方向的事件（内部 tick、状态变化、OpenClaw 指令、紧急事件）。

```sql
CREATE TABLE comm_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    direction   TEXT NOT NULL,           -- "internal", "goldclaw→openclaw", "openclaw→goldclaw"
    event_type  TEXT NOT NULL,           -- "tick", "state_change", "order", "emergency", "status_report"
    payload     TEXT DEFAULT '{}',
    created_at  TEXT NOT NULL
);
```

#### 表 7: investor_snapshots（投资者资产快照 — 每 tick 记录）

每个 tick 记录一次投资者 A/B 的总资产和持仓状态。后台保留完整快照数据，Dashboard 资产曲线仅展示决策点（trade_history）。

```sql
CREATE TABLE investor_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    investor_id TEXT NOT NULL,           -- "A" 或 "B"
    total_assets REAL NOT NULL,          -- 总资产
    action      TEXT NOT NULL DEFAULT 'idle'  -- 当前持仓动作
);
CREATE INDEX idx_snapshots_time ON investor_snapshots(timestamp);
```

### 7.2 信箱输出：Python → OpenClaw（状态文件）

Python 每 tick 将投资者状态从 SQLite 提取，覆写到 `data/state_for_openclaw.json`。OpenClaw cron 唤醒时读取。

**请求 Payload（状态推送）**：

```json
{
  "type": "status_report",
  "timestamp": "2026-04-08T14:15:00Z",
  "system": {
    "state": "IDLE",
    "gold_price": 3025.50,
    "volatility": 0.0012,
    "slope_3min": 0.0003
  },
  "investors": {
    "A": {
      "total_assets": 10250.00,
      "cash": 2048.00,
      "margin_committed": 6160.00,
      "current_action": "cfd_long",
      "entry_price": 3010.00,
      "current_price": 3025.50,
      "tp": 3055.40,
      "sl": 2987.75,
      "nominal_pnl": 1012.50,
      "net_pnl": 960.82,
      "margin_call": 0,
      "pnl_pct": 0.0961,
      "nights_held": 2
    },
    "B": {
      "total_assets": 9800.00,
      "cash": 5000.00,
      "current_action": "cfd_short",
      "margin_committed": 1960.00,
      "entry_price": 3030.00,
      "current_price": 3025.50,
      "tp": 2874.25,
      "sl": 3085.60,
      "nominal_pnl": 58.74,
      "net_pnl": 44.12,
      "margin_call": 0,
      "pnl_pct": -0.02,
      "nights_held": 1
    }
  },
  "warnings": [
    {
      "timestamp": "2026-04-09T10:15:00Z",
      "investor": "B",
      "violation": "cfd_long not allowed for Investor B",
      "original_action": "cfd_long",
      "action_taken": "blocked, continued cfd_short"
    }
  ]
}
```

**TP/SL 说明**: `tp` 和 `sl` 是基于金价的**绝对价格**，不是百分比。SGLN 仓位 tp=0, sl=0。

**warnings（耻辱柱）**: 记录最近 5 条违规。OpenClaw 每次决策前应检查此字段，看到前置警告。

### 7.3 信箱输入：OpenClaw → Python（决策文件）

OpenClaw 在 cron 会话中思考后，将决策写入 `data/orders_from_openclaw.json`。

**响应 Payload**:

```json
{
  "timestamp": "2026-04-08T14:15:00Z",
  "instructions": [
    {
      "investor": "A",
      "action": "cfd_long",
      "margin_pct": 0.80,
      "tp": 3055.40,
      "sl": 2987.75,
      "signal_strength": 0.85,
      "signal_type": "strong_bullish",
      "reasoning": "Polymarket 降息概率 85%"
    },
    {
      "investor": "B",
      "action": "cfd_short",
      "margin_pct": 0.20,
      "tp": 2874.25,
      "sl": 3085.60,
      "signal_strength": 0.82,
      "signal_type": "strong_bullish_consensus",
      "reasoning": "共识达到沸点，预期卖出事实行情"
    }
  ]
}
```

**字段约束**:

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| `timestamp` | string (ISO 8601) | 是 | UTC 时间 |
| `instructions` | array | 是 | 每个 investor 对应一条（当前 A/B，未来可扩展） |
| `instructions[].investor` | enum | 是 | `"A"` 或 `"B"` |
| `instructions[].action` | enum | 是 | 见下方 Action 枚举 |
| `instructions[].margin_pct` | float | 条件 | 0.0-1.0，开仓类时必填 |
| `instructions[].tp` | float | 条件 | 金价绝对止盈价格，CFD 开仓时必填；SGLN 不需要 |
| `instructions[].sl` | float | 条件 | 金价绝对止损价格，CFD 开仓时必填；SGLN 不需要 |
| `instructions[].signal_strength` | float | 否 | 0.0-1.0，仅记录到 trade_history，不参与运算 |
| `instructions[].signal_type` | string | 否 | 最长 200 字符，仅记录 |
| `instructions[].reasoning` | string | 否 | 最长 1000 字符，仅记录 |

**Action 枚举**:

| 值 | 投资者A | 投资者B | 说明 |
|----|---------|---------|------|
| `cfd_long` | 可用 | 不可用 | CFD 做多开仓（需 TP/SL） |
| `cfd_short` | 可用 | 可用 | CFD 做空开仓（需 TP/SL） |
| `sgln_long` | 不可用 | 可用 | SGLN 做多（无 TP/SL） |
| `hold` | 可用 | 可用 | 维持当前仓位 |
| `idle` | 可用 | 可用 | 空仓观望 |
| `close` | 可用 | 可用 | 平掉当前仓位 |

**校验流程（Python 在内存中执行）**:

```
OpenClaw Response → Pydantic 校验 → 合法则 UPDATE SQLite → 非法则 INSERT violations
```

**非法指令处理（耻辱柱机制）**:

1. **延续当前策略** — 该投资者的非法指令被拦截
2. **写入 violations 表** — 记录违规详情（INSERT Only）
3. **下周期通报** — 下次 Webhook 请求的 `warnings` 字段附带违规提示
4. **数据库毫发无损** — 非法指令永远不触碰 investor_state 表

非法组合：
- 投资者 A + `sgln_long` → 拦截
- 投资者 B + `cfd_long` → 拦截
- 开仓但 `margin_pct` 缺失或越界 → 拦截
- CFD 开仓但 `tp` 或 `sl` 缺失 → 拦截

### 7.4 门铃通知（TRIGGER / 止损 / 爆仓 / 止盈）

GoldClaw 触发 TRIGGER 时，POST 到 `OPENCLAW_BRIDGE_URL`（门铃）。紧急事件（止损/爆仓/止盈）也是门铃通知，但 OpenClaw 无需响应。

详细 JSON 格式和字段说明见 `RULES.md` 第 7 节。

**事件类型**: `state_trigger`（需 OpenClaw 响应）/ `margin_call` / `stop_loss` / `take_profit`（纯通知）

---

## 8. 每个功能的完成定义

### F1 金价获取

- **完成 =** 每次调用 `GET https://api.gold-api.com/price/XAU` 返回有效金价
- **成功**: 金价 > 0，记录到价格历史，终端打印 `"[tick] XAU $3025.50"`
- **API 不可用**: 重试 3 次后使用缓存价格，终端打印 `"WARN: API unavailable, using cached price $3020.00"`
- **无缓存且 API 不可用**: 跳过本次 tick，不执行任何交易操作，打印 `"ERROR: No price data, skipping tick"`

### F2 状态机

- **完成 =** 状态转换严格遵循第 6 节规则，具有惯性确认和冷却机制
- **IDLE→WATCH**: 累积斜率超过 THRESHOLD_A 或斜率差值超过 THRESHOLD_B 时切换，终端打印 `"State: IDLE → WATCH"`，重置计时器和参考金价
- **WATCH→TRIGGER**: WATCH 期间斜率超过 THRESHOLD_TRIGGER_SLOPE 或触及止损/止盈/爆仓时触发
- **WATCH→IDLE**: 超过 WATCH_DURATION 且斜率未突破阈值且波动率回落，三个条件同时满足
- **TRIGGER→冷却→IDLE**: 操作执行后进入 SILENCE_PERIOD 冷却期，冷却结束后回到 IDLE
- **Webhook 冷却**: SILENCE_PERIOD 内不发送非紧急 Webhook，止损/爆仓无视冷却
- **状态持久化**: 写入 `data/state.json`（含 state、entered_at、watch_start_price、silence_until），重启后恢复
- **价格历史不足**: 少于 2 个数据点时默认 IDLE

### F3 接收交易指令

- **完成 =** 通过 JSON 文件交换接收 OpenClaw 的投资决策
- **正常流程**: Python 写 state_for_openclaw.json → OpenClaw cron 读 → 写 orders_from_openclaw.json → Python 读 → 校验并执行
- **OpenClaw 未按时写入决策**: 维持当前仓位，不执行新操作，打印 `"WARN: No new orders from OpenClaw, continuing current positions"`
- **响应为空**: 视为 HOLD，维持现状
- **每 3 小时一个周期**: Python 定期推送状态给 OpenClaw，等待响应中的指令

### F4 指令校验

- **完成 =** 所有指令通过 Pydantic Schema 校验
- **合法指令**: 正常执行
- **格式错误** (缺字段、类型错、值越界): 拦截该投资者指令，延续当前策略
- **非法组合** (如投资者B做 cfd_long): 拦截该投资者指令，延续当前策略
- **绝不猜测**: 任何不确定的情况一律延续当前策略
- **耻辱柱记录**: 拦截时写入 SQLite `violations` 表（INSERT Only，数据库毫发无损）
- **下周期通报**: 下次 Webhook POST 的 `warnings` 字段附带违规提示，让 OpenClaw 看到前置警告
- **warnings 保留最近 5 条**: 超出则丢弃最老的

### F5 指令过期检测

- **完成 =** 超过 TTL 的指令自动丢弃
- **TTL = 30 分钟** (可通过 `GOLDCLAW_ORDER_TTL_SECONDS` 配置)
- **过期指令**: 丢弃，维持当前仓位，打印 `"WARN: Instruction expired (age=45min), discarded"`
- **有效指令**: 正常执行

### F6 开仓执行

- **完成 =** 成功建立仓位并扣除费用
- **CFD 做多 (投资者A或B)**:
  1. 计算 `margin = total_assets × margin_pct`
  2. 检查 `cash ≥ margin`，不够则拒绝
  3. 扣除 `spread = margin × 1%`
  4. `actual_margin = margin - spread`
  5. 从 cash 中扣除 margin
  6. 记录 entry_price = 当前金价
  7. 记录 tp 和 sl 为指令中的金价绝对价格
- **CFD 做空 (投资者A或B)**: 同上
- **SGLN 做多 (投资者B)**:
  1. 计算 `investment = total_assets × margin_pct`（margin_pct 在 SGLN 中表示投入比例）
  2. 检查 `cash ≥ investment`
  3. 从 cash 中扣除 investment
  4. 记录 entry_price = 当前金价（SGLN 直接跟踪金价涨跌百分比）
  5. 不设 TP/SL
- **投资者B已有仓位时收到不同类型指令**: 先平掉当前仓位（计算净盈亏），再开新仓位（CFD→SGLN 或 SGLN→CFD）
- **投资者A已有仓位时收到新开仓指令**: 先平掉旧仓位（计算净盈亏），再开新仓
- **现金不足**: 拒绝开仓，记录 `"insufficient_margin: cash=$500, required=$8000"`

### F7 平仓执行

- **完成 =** 计算净盈亏并更新余额
- **CFD 平仓**:
  1. 计算 nominal_pnl
  2. 扣除 FX 转换费 = abs(nominal_pnl) × 0.5%
  3. 扣除累计隔夜利息
  4. net_pnl = nominal_pnl - fx_cost - overnight_interest
  5. cash += actual_margin + net_pnl
  6. 如果 net_pnl < 0 且 |net_pnl| > actual_margin → cash = max(0, cash)，记录亏损
- **SGLN 平仓**:
  1. pnl = investment × (current_price / buy_price - 1)
  2. cash += investment + pnl
- **平仓后**: margin_committed = 0，current_action = "idle"

### F8 持仓盈亏计算

- **完成 =** 每 tick 更新所有持仓的名义盈亏和净盈亏
- **投资者A**: 计算 CFD 做多 nominal_pnl
- **投资者B**: 计算 CFD 做空 nominal_pnl + SGLN pnl
- **总资产**: 严格按公式 `cash + margin + PnL`，actual_margin 必须计入
- **精度**: 保留小数点后 2 位

### F9 止损监控

- **完成 =** 金价触及止损价格时自动平仓
- **CFD 做多止损**: `current_price ≤ sl`（金价跌破止损价）
- **CFD 做空止损**: `current_price ≥ sl`（金价涨破止损价）
- **SGLN 无止损**: SGLN 不设止损，仅通过 OpenClaw 指令平仓
- **触发后**: 执行平仓 → 发送 Webhook → 写入 events

### F10 止盈监控

- **完成 =** 金价触及止盈价格时自动平仓
- **CFD 做多止盈**: `current_price ≥ tp`（金价涨破止盈价）
- **CFD 做空止盈**: `current_price ≤ tp`（金价跌破止盈价）
- **SGLN 无止盈**: SGLN 不设止盈，仅通过 OpenClaw 指令平仓
- **触发后**: 执行平仓 → 发送 Webhook → 写入 events

### F11 爆仓检测

- **完成 =** 保证金归零时自动平仓
- **条件**: `net_pnl ≤ -actual_margin`（亏损已吃完全部保证金）
- **触发后**:
  1. 立即平仓
  2. cash = max(0, cash + net_pnl)
  3. `margin_call = 1`
  4. 发送 Webhook (priority = "urgent")
  5. 写入 events `"MARGIN_CALL: investor A, loss $6160"`
- **SGLN 无爆仓风险**: SGLN 无杠杆，不存在爆仓

### F12 状态输出

- **完成 =** 每 tick 原子写入 `data/python_to_openclaw.json`
- **SQLite 事务**: 所有状态更新在单个事务中完成（BEGIN → UPDATE/INSERT → COMMIT）
- **trade_history 追加**: 每次交易操作后 INSERT 一条记录

### F13 Webhook 通知

- **完成 =** TRIGGER 时发送 HTTP POST 到 Bridge URL（门铃）
- **URL**: 从环境变量 `OPENCLAW_BRIDGE_URL` 读取（可选）
- **URL 为空**: 跳过门铃，仅写信箱文件，等 OpenClaw 下次 cron
- **超时 30 秒**: 到时间强制断开，不重试
- **发送成功**: 日志 `"Bridge notified: margin_call A"`
- **发送失败**: 日志 `"WARN: Bridge POST failed: timeout"`，引擎继续运行

### F14 数据库安全

- **完成 =** SQLite ACID 事务保护所有写操作
- **事务流程**: `BEGIN → UPDATE investor_state → INSERT trade_history → COMMIT`
- **异常回滚**: 任何步骤出错自动 `ROLLBACK`，数据不会处于不一致状态
- **WAL 模式**: 启用 Write-Ahead Logging，提高并发性能

### F15 LLM 误写隔离

- **完成 =** OpenClaw 永远无法直接操作 SQLite
- **隔离机制**: 所有指令通过 Webhook Response → Pydantic 校验 → Python 写入 SQLite
- **校验失败**: 数据库毫发无损，违规仅记录到 violations 表
- **不存在文件损坏**: SQLite 二进制格式，LLM 无法误写

### F16 优雅启动/关闭

- **启动**: 检查目录 → 加载配置 → 恢复状态 → 启动调度器 → 打印启动信息
- **Ctrl+C**: 完成当前 tick → 保存状态 → 退出调度器 → 打印 `"GoldClaw stopped gracefully"`

### F17 日志记录

- **完成 =** 所有关键操作写入 `trade_history` 表和终端日志
- **trade_history**: 每次交易 INSERT 一条记录（INSERT Only，不修改不删除）
- **终端输出**: `2026-04-08T14:15:00Z [INFO] tick: XAU $3025.50, state=IDLE`
- **violations 表**: 记录所有 LLM 违规操作

### F18 幻觉检测（数值突变拦截）

- **完成 =** 每次执行交易后，对比交易前后的关键数值变化，防止 OpenClaw 幻觉导致异常交易
- **检测逻辑**: 执行交易后，对比 `交易前 total_assets` 和 `交易后 total_assets`（或 margin 变化）
  - 如果 `|变化量| / 交易前 total_assets > THRESHOLD`（默认 50%），视为幻觉
  - 如果 margin_pct 突变超过上一周期的 3 倍（如上期 20%，本期 85%），视为异常
- **阈值**: `GOLDCLAW_HALLUCINATION_THRESHOLD = 0.5`（可配置）
- **触发后**:
  1. 忽略本次交易，ROLLBACK 事务
  2. 恢复交易前的投资者状态（从 SQLite 读回旧值）
  3. INSERT violations 表，记录幻觉详情
  4. 下次 Webhook `warnings` 字段通报 OpenClaw
- **不触发**: 变化在合理范围内的交易正常执行

---

## 9. 错误状态

### 9.1 金价 API 不可用

| 场景 | 表现 | 处理 |
|------|------|------|
| API 超时 (10s) | 单次请求超时 | 重试 (最多 3 次) |
| API 返回非 200 | HTTP 4xx/5xx | 重试 (最多 3 次) |
| API 返回无效数据 | 金价为 0 或负数 | 视为失败，使用缓存价格 |
| 连续 3 次失败 | 所有重试耗尽 | 使用最后缓存价格，**不执行新交易** |
| 无缓存 + API 失败 | 首次运行即 API 不可用 | 跳过 tick，等待下次 |

### 9.2 OpenClaw 通信异常

| 场景 | 表现 | 处理 |
|------|------|------|
| URL 未配置 | 空字符串 | 跳过 Webhook，引擎独立运行（仅自动止损止盈） |
| 连接超时 | 30 秒无响应 | 放弃本次决策，维持当前仓位，记录日志 |
| 连接拒绝 | OpenClaw 未启动 | 放弃本次决策，维持当前仓位，记录日志 |
| Response 格式错误 | JSON 解析失败 | 拒收，数据库不变，记录 violations |
| Response 字段缺失 | Pydantic 校验失败 | 拒收该投资者指令，延续当前策略，记录 violations |
| Response 非法值 (margin=2.0) | Pydantic 校验失败 | 拒收，记录 violations |
| 指令过期 | Response 中 timestamp > 30 分钟 | 丢弃指令，维持当前仓位 |

### 9.3 SQLite 异常

| 场景 | 表现 | 处理 |
|------|------|------|
| 数据库文件损坏 | SQLite 异常 | 从自动备份恢复，无备份则重新初始化 |
| 磁盘满 | 写入失败 | 记录日志，引擎继续运行（内存中计算） |
| 事务冲突 | SQLITE_BUSY | 自动重试（WAL 模式下极少发生） |

> **数据安全保证**: SQLite ACID 事务 + WAL 模式 + Pydantic 校验层，三层保护确保 LLM 误写永远无法触及底层数据。

### 9.4 交易逻辑异常

| 场景 | 表现 | 处理 |
|------|------|------|
| 现金不足开仓 | cash < required margin | 拒绝开仓，记录日志 |
| 投资者 A 收到 sgln_long | 收到 sgln_long 指令 | 拦截，延续当前策略，记录耻辱柱 |
| 投资者 B 收到 cfd_long | 收到 cfd_long 指令 | 拦截，延续当前策略，记录耻辱柱 |
| 已有仓位又开仓 | 收到新开仓指令 | 先平旧仓，再开新仓 |
| 平仓后余额为负 | 亏损超过保证金 | cash = max(0, ...)，记录债务 |
| 爆仓 + 止损同时触发 | 同一 tick 两个条件 | 按爆仓处理（更严重） |

---

## 10. 不做什么（v1.0 排除）

以下功能 **明确不包含** 在 v1.0 版本中：

1. **不接真实交易所**: 这是纯模拟系统，不连接任何真实交易所 API
2. **不做用户认证**: 本地单用户运行，无登录系统
3. **不做实时推送**: 没有 WebSocket/SSE，OpenClaw 只能通过读 JSON 文件获取状态
6. **不做策略回测**: 不支持导入历史数据进行策略验证
7. **不做多品种**: 只支持 XAU（黄金），不支持白银、原油等
8. **不做加密通信**: Webhook 不做签名验证，JSON 文件无加密
9. **不做自动调参**: 状态机阈值、费率等参数通过 .env 手动配置，不支持运行时修改
10. **不做分布式**: 单进程单机运行，不支持多实例部署
11. **不做邮件/IM 通知**: 只有 Webhook 一种通知方式
12. **v1.0 只支持投资者 A 和 B**: 但 JSON Schema 和代码架构需为未来增加投资者 C/D/E 预留扩展空间——`instructions` 数组和 `investors` 对象不硬编码为固定长度，投资者画像通过配置文件而非硬编码定义

---

## 11. 验收清单

### 11.1 金价获取

- [ ] 运行 `python main.py`，终端每 15 分钟打印一次金价
- [ ] 拔掉网线后，引擎使用缓存价格继续运行，不崩溃
- [ ] API 返回错误时，重试 3 次后打印 WARN 日志

### 11.2 状态机

- [ ] 默认状态为 IDLE，每 15 分钟执行一次 tick
- [ ] 累积斜率超过 THRESHOLD_A 时切换到 WATCH，tick 频率变为 3 分钟
- [ ] 斜率差值突变（abs(Current_Slope - Prev_Slope) > THRESHOLD_B）时也切换到 WATCH
- [ ] 进入 WATCH 时重置计时器和参考金价
- [ ] WATCH 期间斜率超过 THRESHOLD_TRIGGER_SLOPE 时进入 TRIGGER
- [ ] WATCH 超过 WATCH_DURATION 且斜率未突破阈值且回落 → 退回 IDLE
- [ ] 止损/止盈/爆仓时进入 TRIGGER
- [ ] TRIGGER 操作后进入 SILENCE_PERIOD 冷却期
- [ ] 冷却期间不发送非紧急 Webhook，止损/爆仓无视冷却
- [ ] 冷却结束后自动回到 IDLE
- [ ] 重启程序后状态机恢复到上次的状态（含 watch_start_price、silence_until）

### 11.3 交易指令处理

- [ ] 手动写入一个合法的 `openclaw_to_python.json`（tp/sl 为金价绝对价格），引擎在下一个 tick 执行交易
- [ ] 写入一个缺字段的 JSON，引擎拦截该投资者指令，延续当前策略
- [ ] 写入一个 35 分钟前的指令，引擎打印 "expired" 并丢弃
- [ ] 写入 `margin_pct: 2.0`，引擎拦截并记录耻辱柱
- [ ] 投资者 A 收到 `sgln_long`，引擎拦截，warnings 数组中出现违规记录
- [ ] 投资者 B 收到 `cfd_long`，引擎拦截，warnings 数组中出现违规记录
- [ ] 下一个 tick 的 `python_to_openclaw.json` 中 `warnings` 字段包含前置提示给 OpenClaw

### 11.4 投资者 A 盈亏计算

- [ ] CFD 做多：金价上涨时 nominal_pnl > 0，下跌时 < 0
- [ ] CFD 做空：金价下跌时 nominal_pnl > 0，上涨时 < 0（投资者 A 现在可以做空）
- [ ] 开仓时 cash 减少（扣除 margin），spread 已从 margin 中扣除
- [ ] 平仓时 cash 增加（margin + net_pnl），FX 费和隔夜利息已扣除
- [ ] 20x 杠杆：金价变动 0.5% 时，PnL 变动约 10%
- [ ] 投资者 A 收到 `sgln_long` 指令时被拦截，延续当前策略

### 11.5 投资者 B 盈亏计算

- [ ] CFD 做空：金价下跌时 nominal_pnl > 0，上涨时 < 0
- [ ] SGLN 做多：金价上涨时 pnl > 0，pnl = investment × (gold_price/entry_gold_price - 1)
- [ ] SGLN 无交易成本、无 TP/SL
- [ ] 投资者 B 同一时间只有一个仓位（CFD 或 SGLN，互斥）
- [ ] 投资者 B 从 CFD 切换到 SGLN（或反向）时，先平旧仓再开新仓
- [ ] 投资者 B 收到 `cfd_long` 指令时被拦截，记录耻辱柱

### 11.6 止损止盈

- [ ] 金价跌至止损价格时引擎自动平仓（CFD 做多：current_price ≤ sl_price）
- [ ] 金价涨至止盈价格时引擎自动平仓（CFD 做多：current_price ≥ tp_price）
- [ ] CFD 做空止损止盈方向正确（止损是金价上涨触发，止盈是金价下跌触发）
- [ ] SGLN 无止损止盈，仅通过 OpenClaw 指令平仓

### 11.7 爆仓

- [ ] 金价剧烈变动导致保证金归零，引擎自动平仓
- [ ] 爆仓后 `margin_call = 1`，cash 不为负
- [ ] Webhook 发送成功，payload 包含完整仓位快照
- [ ] Webhook 超时时引擎不崩溃，日志记录错误

### 11.8 SQLite 数据库

- [ ] `data/goldclaw.db` 存在且包含 4 张表（investor_state, trade_history, system_state, violations）
- [ ] 首次运行自动建表并初始化投资者 A/B 数据
- [ ] investor_state 每个 tick 更新，trade_history 每次交易 INSERT
- [ ] 所有写操作在事务中完成，异常时自动 ROLLBACK
- [ ] 删除 goldclaw.db 后重启，引擎自动重建

### 11.9 健壮性

- [ ] 连续运行 24 小时不崩溃、不内存泄漏
- [ ] OpenClaw Webhook 一直超时，引擎持续正常运行（自动止损止盈不受影响）
- [ ] OpenClaw Response 返回空 JSON `{}`，引擎不崩溃，视为 HOLD
- [ ] 收到 10 条连续非法指令，引擎全部拒绝，不执行任何错误交易
- [ ] OpenClaw 返回 margin_pct=0.99（几乎全仓），引擎正常执行
- [ ] OpenClaw 返回 margin_pct=0.99 导致 total_assets 变化超过 50%，幻觉检测触发，ROLLBACK 交易
- [ ] 幻觉检测触发后 violations 表中有记录，下次 Webhook warnings 字段包含通报
- [ ] Ctrl+C 后引擎打印 "stopped gracefully"，SQLite 数据完整
- [ ] Ctrl+C 后引擎打印 "stopped gracefully"，data/ 文件完整

---

## 12. 项目结构

```
GoldClaw/
├── app_main.py                      # macOS App 入口（pywebview 原生窗口）
├── run.py                           # CLI 入口（Engine + Dashboard）
├── main.py                          # CLI 入口（仅 Engine）
├── openclaw_bridge.py               # 门铃接收器（已集成到 dashboard_api）
├── dashboard_api.py                 # Dashboard + Bridge REST API（FastAPI，端口 8089）
├── build_dmg.sh                     # DMG 构建脚本
├── build.sh                         # Tarball 构建脚本
├── requirements.txt                 # 依赖
├── .env.example                     # 环境变量模板
├── .gitignore
│
├── dashboard/                       # Dashboard 前端
│   ├── index.html
│   └── static/
│       ├── style.css
│       ├── app.js
│       └── app_icon.icns
│
├── docs/                            # 开发文档
│   └── dashboard_dev_plan.md
│
├── config/                          # 配置层
│   ├── __init__.py
│   ├── settings.py                  # pydantic-settings 配置
│   └── defaults.py                  # 默认常量
│
├── profiles/                        # 投资者画像配置（未来扩展C/D/E只需加文件）
│   ├── investor_a.yaml              # 投资者A参数（杠杆、费率、允许的action）
│   └── investor_b.yaml              # 投资者B参数
│
├── app/                             # 应用层
│   ├── __init__.py
│   ├── scheduler.py                 # APScheduler 调度
│   └── engine.py                    # 主编排引擎
│
├── internal/                        # 业务逻辑层
│   ├── __init__.py
│   ├── state_machine/               # 状态机
│   │   ├── __init__.py
│   │   ├── machine.py
│   │   └── states.py
│   ├── price/                       # 金价模块
│   │   ├── __init__.py
│   │   ├── fetcher.py               # API 客户端
│   │   ├── history.py               # 价格历史缓冲
│   │   └── volatility.py            # 波动率/斜率计算
│   ├── investor/                    # 投资者模块
│   │   ├── __init__.py
│   │   ├── base.py                  # 抽象基类
│   │   ├── investor_a.py            # 投资者A
│   │   ├── investor_b.py            # 投资者B
│   │   └── pnl.py                   # 盈亏纯函数
│   ├── db/                          # 数据库层
│   │   ├── __init__.py
│   │   ├── connection.py            # SQLite 连接管理（WAL 模式）
│   │   ├── migrations.py            # 建表/迁移
│   │   ├── repository.py            # 数据访问层（InvestorRepository + DashboardRepository）
│   │   └── backup.py                # 数据库备份/恢复/滚动保留
│   ├── exchange/                    # 通信层（信箱 + 门铃）
│   │   ├── __init__.py
│   │   ├── schema.py                # Pydantic Schema
│   │   ├── webhook_client.py        # 信箱文件交换 + 门铃 POST
│   │   └── validator.py             # 指令校验 + 幻觉检测
│   └── exception/                   # 异常处理
│       ├── __init__.py
│       ├── errors.py                # 自定义异常
│       └── handler.py               # 错误处理器
│
├── data/                            # 运行时数据（gitignored）
│   ├── goldclaw.db                  # SQLite 数据库（所有数据在此）
│   ├── state_for_openclaw.json      # 信箱输出（Python → OpenClaw）
│   └── orders_from_openclaw.json    # 信箱输入（OpenClaw → Python）
│
└── tests/                           # 测试
    ├── __init__.py
    ├── test_pnl_calculations.py     # 21 tests
    ├── test_state_machine.py        # 16 tests
    ├── test_schema_validation.py    # 24 tests
    ├── test_investor_a.py           # 20 tests
    ├── test_investor_b.py           # 14 tests
    └── test_integration.py          # 25 tests
```

---

## 13. 依赖环境

### requirements.txt

```
pydantic>=2.5.0
pydantic-settings>=2.1.0
APScheduler>=3.10.0
httpx>=0.27.0
fastapi>=0.110.0
uvicorn>=0.29.0
```

> **注意**: SQLite 是 Python 标准库内置模块（`sqlite3`），无需额外安装依赖。

### 环境变量

```bash
# .env.example

# 金价 API
GOLDCLAW_GOLD_API_URL=https://api.gold-api.com/price/XAU
GOLDCLAW_GOLD_API_TIMEOUT=10.0
GOLDCLAW_GOLD_API_RETRIES=3

# OpenClaw Bridge（门铃，可选。未配置则退化为纯信箱模式）
GOLDCLAW_OPENCLAW_BRIDGE_URL=
GOLDCLAW_OPENCLAW_BRIDGE_TIMEOUT=30.0

# SQLite 数据库路径
GOLDCLAW_DB_PATH=data/goldclaw.db

# 初始资金（OpenClaw 可通过指令覆盖）
GOLDCLAW_INVESTOR_A_INITIAL_CASH=10000.0
GOLDCLAW_INVESTOR_B_INITIAL_CASH=10000.0

# 费率
GOLDCLAW_CFD_SPREAD=0.01
GOLDCLAW_CFD_OVERNIGHT=0.0082
GOLDCLAW_CFD_FX=0.005
GOLDCLAW_CFD_LEVERAGE=20

# 状态机阈值
GOLDCLAW_CYCLE_X=15
GOLDCLAW_THRESHOLD_A=0.0015
GOLDCLAW_THRESHOLD_B=0.001
GOLDCLAW_WATCH_DURATION=30
GOLDCLAW_TRIGGER_SLOPE=0.001
GOLDCLAW_SILENCE_PERIOD=15
GOLDCLAW_ORDER_TTL_SECONDS=1800

# 幻觉检测
GOLDCLAW_HALLUCINATION_THRESHOLD=0.5

# 调度间隔
GOLDCLAW_MAIN_TICK_MINUTES=15
GOLDCLAW_WATCH_TICK_MINUTES=3

# SGLN 价格比率
GOLDCLAW_SGLN_GOLD_RATIO=3.215
```

---

## 14. 版本迭代

| 版本 | 内容 | 状态 |
|------|------|------|
| v0.1 | 核心引擎：数据库+金价+盈亏+状态机+通信+引擎编排+95测试 | **已完成** |
| v0.2 | 集成测试：25 个集成测试覆盖完整交易生命周期 | **已完成** |
| v0.3 | OpenClaw 联调：23 步端到端验证全通过 + Bridge + Dashboard 骨架 | **已完成** |
| v0.4 | 数据库备份 + 中英文切换 + 投资者资产曲线 + 每 tick 快照 | **已完成** |
| v0.5 | 指令过期检测 (F5) + 门铃后轮询 + 历史回测 | 待开发 |
| v1.0 | 完整系统上线 | 待开发 |
