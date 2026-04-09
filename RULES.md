# RULES.md — GoldClaw × OpenClaw 通信规范

> 本文档定义 GoldClaw（Python 引擎）与 OpenClaw（LLM 决策系统）之间的通信协议。
> OpenClaw 开发者只需阅读本文件即可完成对接。

---

## 1. 通信架构

```
┌─────────────┐    信箱（每 tick 覆写）     ┌─────────────┐
│  GoldClaw   │ ──── state_for_openclaw.json ──►│  OpenClaw  │
│  (Python)   │ ◄─── orders_from_openclaw.json ──│  (LLM)    │
│             │                                │            │
│             │    门铃（TRIGGER 时 POST）       │            │
│             │ ──── POST /emergency ──────────►│  Bridge   │
└─────────────┘                                └─────────────┘
```

- **信箱**：JSON 文件交换。GoldClaw 每 tick 覆写状态，OpenClaw cron 时读取后写决策。
- **门铃**：TRIGGER 时 GoldClaw POST 到 `OPENCLAW_BRIDGE_URL`，强制唤醒 OpenClaw。
- **SQLite 是真相源**：JSON 只是信件副本，OpenClaw 永远不能直接操作数据库。

---

## 2. 文件清单

| 文件 | 写入方 | 读取方 | 频率 |
|------|--------|--------|------|
| `data/state_for_openclaw.json` | GoldClaw（每 tick） | OpenClaw（cron） | 每 15/3 分钟 |
| `data/orders_from_openclaw.json` | OpenClaw（cron） | GoldClaw（每 tick） | 每 3 小时或紧急触发 |

---

## 3. GoldClaw → OpenClaw（状态文件）

**文件**: `data/state_for_openclaw.json`
**写入时机**: 每个 tick（15 分钟或 3 分钟）覆写

### 完整示例

```json
{
  "type": "status_report",
  "timestamp": "2026-04-09T00:15:00Z",
  "system": {
    "state": "IDLE",
    "gold_price": 4704.30,
    "volatility": 0.0037,
    "slope_3min": 0.0021
  },
  "investors": {
    "A": {
      "total_assets": 10250.00,
      "cash": 2048.00,
      "margin_committed": 6160.00,
      "current_action": "cfd_long",
      "entry_price": 4680.00,
      "current_price": 4704.30,
      "tp": 4750.00,
      "sl": 4630.00,
      "nominal_pnl": 1012.50,
      "net_pnl": 960.82,
      "margin_call": 0,
      "pnl_pct": 0.0961,
      "nights_held": 2
    },
    "B": {
      "total_assets": 9800.00,
      "cash": 5000.00,
      "margin_committed": 0,
      "current_action": "idle",
      "entry_price": null,
      "current_price": 4704.30,
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

### 字段说明

| 路径 | 类型 | 说明 |
|------|------|------|
| `type` | string | 固定 `"status_report"` |
| `timestamp` | string | ISO 8601 UTC |
| `system.state` | enum | `"IDLE"` / `"WATCH"` / `"TRIGGER"` |
| `system.gold_price` | float | 当前金价（USD/盎司） |
| `system.volatility` | float | 归一化波动率 |
| `system.slope_3min` | float | 归一化斜率 |
| `investors.{ID}.total_assets` | float | 总资产 = cash + margin + pnl |
| `investors.{ID}.cash` | float | 可用现金 |
| `investors.{ID}.margin_committed` | float | 已投入保证金（空仓为 0） |
| `investors.{ID}.current_action` | enum | 当前持仓动作（见 Action 枚举） |
| `investors.{ID}.entry_price` | float/null | 开仓金价（空仓为 null） |
| `investors.{ID}.current_price` | float | 最近金价 |
| `investors.{ID}.tp` | float | 止盈价格（**金价绝对价格**，SGLN 为 0） |
| `investors.{ID}.sl` | float | 止损价格（**金价绝对价格**，SGLN 为 0） |
| `investors.{ID}.nominal_pnl` | float | 名义盈亏 |
| `investors.{ID}.net_pnl` | float | 净盈亏（扣费后） |
| `investors.{ID}.margin_call` | int | 0=正常, 1=已爆仓 |
| `investors.{ID}.pnl_pct` | float | 收益率 |
| `investors.{ID}.nights_held` | int | 持仓过夜天数 |
| `warnings[]` | array | 最近 5 条违规记录 |

### 有 warnings 时的示例

```json
{
  "type": "status_report",
  "timestamp": "2026-04-09T00:15:00Z",
  "system": { "state": "IDLE", "gold_price": 4704.30, "volatility": 0.0037, "slope_3min": 0.0021 },
  "investors": { "A": { "...": "..." }, "B": { "...": "..." } },
  "warnings": [
    {
      "timestamp": "2026-04-09T10:15:00Z",
      "investor": "B",
      "violation": "Investor B cannot cfd_long",
      "original_action": "cfd_long",
      "action_taken": "blocked, continued current strategy"
    }
  ]
}
```

---

## 4. OpenClaw → GoldClaw（决策文件）

**文件**: `data/orders_from_openclaw.json`
**写入时机**: OpenClaw cron 决策完成后
**处理**: GoldClaw 下个 tick 读取、校验、执行，然后重命名为 `orders_processed_[ts].json`

### 完整示例 — 开仓

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
      "signal_strength": 0.85,
      "signal_type": "strong_bullish",
      "reasoning": "降息概率 85%，金价突破 4700 支撑位"
    },
    {
      "investor": "B",
      "action": "sgln_long",
      "margin_pct": 0.50,
      "tp": 0,
      "sl": 0,
      "signal_strength": 0.70,
      "signal_type": "moderate_bullish",
      "reasoning": "长期看涨，SGLN 防御性建仓"
    }
  ]
}
```

### 完整示例 — 维持/平仓

```json
{
  "timestamp": "2026-04-09T06:00:00Z",
  "instructions": [
    {
      "investor": "A",
      "action": "hold"
    },
    {
      "investor": "B",
      "action": "close"
    }
  ]
}
```

### 完整示例 — 做空

```json
{
  "timestamp": "2026-04-09T09:00:00Z",
  "instructions": [
    {
      "investor": "A",
      "action": "cfd_short",
      "margin_pct": 0.60,
      "tp": 4600.00,
      "sl": 4780.00,
      "signal_strength": 0.78,
      "signal_type": "bearish_reversal",
      "reasoning": "金价触及阻力位 4750，预期回调"
    },
    {
      "investor": "B",
      "action": "cfd_short",
      "margin_pct": 0.30,
      "tp": 4620.00,
      "sl": 4770.00,
      "signal_strength": 0.65,
      "signal_type": "bearish_reversal",
      "reasoning": "跟随做空信号，轻仓试探"
    }
  ]
}
```

### 完整示例 — 空仓观望

```json
{
  "timestamp": "2026-04-09T12:00:00Z",
  "instructions": [
    {
      "investor": "A",
      "action": "idle"
    },
    {
      "investor": "B",
      "action": "idle"
    }
  ]
}
```

---

## 5. 字段约束

### instructions[] 字段

| 字段 | 类型 | 必填 | 约束 |
|------|------|------|------|
| `investor` | string | 是 | `"A"` 或 `"B"`（单字母大写） |
| `action` | enum | 是 | 见 Action 枚举 |
| `margin_pct` | float | 条件 | 0.0-1.0，开仓类（cfd_long/cfd_short/sgln_long）必填 |
| `tp` | float | 条件 | 金价绝对止盈价格，CFD 开仓必填；SGLN 填 0 或不填 |
| `sl` | float | 条件 | 金价绝对止损价格，CFD 开仓必填；SGLN 填 0 或不填 |
| `signal_strength` | float | 否 | 0.0-1.0，仅记录 |
| `signal_type` | string | 否 | 最长 200 字符，仅记录 |
| `reasoning` | string | 否 | 最长 1000 字符，仅记录 |

### Action 枚举

| 值 | 投资者A | 投资者B | 需要 margin_pct | 需要 tp/sl | 说明 |
|----|---------|---------|----------------|------------|------|
| `cfd_long` | ✅ | ❌ | 是 | 是 | CFD 做多开仓 |
| `cfd_short` | ✅ | ✅ | 是 | 是 | CFD 做空开仓 |
| `sgln_long` | ❌ | ✅ | 是 | 否 | SGLN 做多（无杠杆、无费用） |
| `hold` | ✅ | ✅ | 否 | 否 | 维持当前仓位 |
| `idle` | ✅ | ✅ | 否 | 否 | 空仓观望 |
| `close` | ✅ | ✅ | 否 | 否 | 平掉当前仓位 |

---

## 6. 校验规则（GoldClaw 侧自动执行）

GoldClaw 读取 `orders_from_openclaw.json` 后，会执行以下校验：

| 规则 | 触发条件 | 处理 |
|------|----------|------|
| 格式校验 | JSON 解析失败或字段类型错误 | 拒收，记录 violations |
| 权限校验 | A 尝试 sgln_long，或 B 尝试 cfd_long | 拦截该投资者指令，记录 violations |
| margin_pct 缺失 | 开仓类 action 但 margin_pct=0 | 拒收，记录 violations |
| tp/sl 缺失 | CFD 开仓但 tp=0 或 sl=0 | 拒收，记录 violations |
| 幻觉检测 | 交易后 total_assets 变化 > 50% | ROLLBACK，记录 violations |
| 指令过期 | timestamp 超过 30 分钟 | 丢弃，维持当前仓位 |

被拦截的指令会出现在下次状态文件的 `warnings` 字段中。

---

## 7. 门铃（紧急通知）

当 GoldClaw 触发 TRIGGER 时，会 POST 到 `OPENCLAW_BRIDGE_URL`。

### 门铃 Payload

```json
{
  "type": "emergency",
  "event": "state_trigger",
  "priority": "urgent",
  "timestamp": "2026-04-09T00:15:00Z",
  "investor": "",
  "gold_price": 4750.00,
  "action_taken": "notifying_openclaw",
  "message": "TRIGGER: slope exceeded threshold, gold price $4750.00"
}
```

### 爆仓通知示例

```json
{
  "type": "emergency",
  "event": "margin_call",
  "priority": "urgent",
  "timestamp": "2026-04-09T00:15:00Z",
  "investor": "A",
  "gold_price": 4580.00,
  "action_taken": "auto_close_position",
  "message": "Investor A margin call at $4580.00, auto closed"
}
```

### event 枚举

| 值 | 说明 | OpenClaw 需要响应 |
|----|------|-------------------|
| `state_trigger` | 状态机触发（趋势确认） | **是** — 写决策文件 |
| `margin_call` | 爆仓自动平仓 | 否（纯通知） |
| `stop_loss` | 止损自动平仓 | 否（纯通知） |
| `take_profit` | 止盈自动平仓 | 否（纯通知） |

---

## 8. 投资者模型速查

### 投资者 A — CFD 1:20 趋势收割者

- **工具**: CFD 做多 (`cfd_long`) 或做空 (`cfd_short`)
- **杠杆**: 20x
- **费率**: Spread 1%（开仓）、隔夜 0.82%/晚、FX 0.5%（平仓）
- **约束**: 同一时间最多 1 个仓位

### 投资者 B — SGLN 防御性狙击手

- **工具**: CFD 做空 (`cfd_short`) **或** SGLN 做多 (`sgln_long`)，互斥
- **CFD**: 杠杆 20x，费率同 A
- **SGLN**: 无杠杆、无费用、无 TP/SL
- **约束**: 同一时间只有 1 个仓位，CFD 和 SGLN 不能同时持有

---

## 9. TP/SL 说明

- `tp` 和 `sl` 是金价的**绝对价格**，不是百分比
- 例如金价 4700 时，止盈 2% 应写 `tp: 4794.00`（= 4700 × 1.02）
- SGLN 不设 TP/SL，写 `0` 或不填
- CFD 做多止损：金价跌破 sl 触发
- CFD 做空止损：金价涨破 sl 触发
