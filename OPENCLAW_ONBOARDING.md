# OPENCLAW_ONBOARDING.md — OpenClaw 接入联调清单

> 本文档指导 OpenClaw 接入 GoldClaw 的完整联调流程。
> 读这份文件 + `RULES.md` 即可开始。

---

## 一、GoldClaw 侧准备工作

### 1. 启动 GoldClaw 并验证输出

```bash
source .venv/bin/activate
python main.py
```

等 1 个 tick 后，检查 `data/state_for_openclaw.json` 是否生成、内容是否完整。Ctrl+C 关闭。

### 2. 手动模拟一次 OpenClaw 决策

编辑 `data/orders_from_openclaw.json`，写入测试指令：

```json
{
  "timestamp": "2026-04-09T12:00:00Z",
  "instructions": [
    {
      "investor": "A",
      "action": "cfd_long",
      "margin_pct": 0.8,
      "tp": 4800.00,
      "sl": 4600.00,
      "reasoning": "接入测试"
    },
    {
      "investor": "B",
      "action": "idle"
    }
  ]
}
```

再启动 GoldClaw，观察日志是否出现 `Processing orders from OpenClaw`，然后检查数据库：

```bash
sqlite3 data/goldclaw.db "SELECT current_action, margin_committed FROM investor_state"
```

### 3. 确定文件共享方式

GoldClaw 和 OpenClaw 必须能读写同一个 `data/` 目录。

- **同机运行**：OpenClaw 直接读写同一个 `data/` 目录（最简单，推荐先这样）
- **异机运行**：需要共享文件夹或云存储同步（后期再考虑）

### 4. 门铃 Bridge（可选，v1 联调可跳过）

如果需要 TRIGGER 紧急唤醒：

- 在 `.env` 设置 `GOLDCLAW_OPENCLAW_BRIDGE_URL=http://localhost:8000/emergency`
- OpenClaw 侧需要一个 FastAPI 服务接收 POST（几行代码）
- **v1 联调可以先不设**，靠 OpenClaw cron 定时读信箱即可

---

## 二、OpenClaw 侧需要做的事

### 1. 读 RULES.md

这是唯一需要读的规范文档。包含完整的 JSON 格式、字段约束、示例。

### 2. 每次会话的流程

```
1. 读 data/state_for_openclaw.json → 了解当前状态
2. 分析金价趋势、投资者仓位、warnings
3. 做决策
4. 写 data/orders_from_openclaw.json → 格式严格按 RULES.md
```

### 3. 写文件前的铁律

- `investor` 必须是 `"A"` 或 `"B"`（大写单字母）
- `action` 必须在权限表内（A 不能 `sgln_long`，B 不能 `cfd_long`）
- 开仓类必须提供 `margin_pct`（0.0-1.0）
- CFD 开仓必须提供 `tp` 和 `sl`（金价绝对价格，不是百分比）
- SGLN 不需要 tp/sl
- `timestamp` 用 UTC

### 4. 从简单开始

联调顺序：

1. 先发 `idle` → 验证文件被读取
2. 再发 `cfd_long`（A）+ `idle`（B）→ 验证开仓
3. 再发 `hold` → 验证维持仓位
4. 再发 `close` → 验证平仓
5. 尝试发一个非法指令（A 做 `sgln_long`）→ 验证被拦截，检查 warnings

---

## 三、联调验证检查点

| # | 验证项 | 怎么确认 |
|---|--------|----------|
| 1 | GoldClaw 写出状态文件 | `cat data/state_for_openclaw.json` |
| 2 | OpenClaw 写入决策文件 | 文件存在于 `data/orders_from_openclaw.json` |
| 3 | GoldClaw 读取并执行 | 日志出现 `Processing orders` |
| 4 | 开仓成功 | `sqlite3 data/goldclaw.db "SELECT current_action, margin_committed FROM investor_state"` |
| 5 | 盈亏计算 | 金价变化后检查 `nominal_pnl` 是否更新 |
| 6 | TP/SL 触发 | 日志出现 `take_profit` 或 `stop_loss` |
| 7 | 平仓记录 | `sqlite3 data/goldclaw.db "SELECT * FROM trade_history ORDER BY id DESC LIMIT 5"` |
| 8 | 非法指令被拦截 | `sqlite3 data/goldclaw.db "SELECT * FROM violations"` |
| 9 | 状态文件含 warnings | `state_for_openclaw.json` 的 `warnings` 数组有内容 |
| 10 | 文件被重命名 | `data/orders_processed_*.json` 存在 |

---

## 四、推荐联调节奏

```
第1轮：手动写 JSON → 确认 GoldClaw 能捡起执行
第2轮：OpenClaw 发 idle → 确认文件交换通路通
第3轮：OpenClaw 发开仓指令 → 确认交易执行
第4轮：等几个 tick → 确认盈亏跟踪
第5轮：OpenClaw 发平仓 → 确认完整闭环
第6轮：故意发非法指令 → 确认防护机制生效
```
