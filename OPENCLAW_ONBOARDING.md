# OPENCLAW_ONBOARDING.md — OpenClaw 接入联调清单

> 本文档指导 OpenClaw 接入 GoldClaw 的完整联调流程。
> 读这份文件 + `RULES.md` 即可开始。

---

## 零、联调前 TODO 清单

按顺序逐项完成，每完成一项打勾。

### 环境配置

- [x] **安装新依赖**（bridge 需要 fastapi + uvicorn）
  ```bash
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

- [x] **配置 .env — 检查以下变量**
  > 已配置 Bridge URL: `http://localhost:8088/emergency`（端口 8000 被 olmx 占用，改用 8088）
  ```
  # Gold API（已配好，确认能访问）
  GOLD_API_URL=https://api.gold-api.com/price/XAU

  # OpenClaw Bridge（v1 联调先留空，后续填）
  OPENCLAW_BRIDGE_URL=
  OPENCLAW_BRIDGE_TIMEOUT=30

  # Database（默认即可）
  DB_PATH=data/goldclaw.db

  # 初始资金（默认 10000，按需调整）
  INITIAL_CASH_A=10000
  INITIAL_CASH_B=10000

  # 状态机阈值（默认即可，联调时可调小便于触发）
  CYCLE_X=5
  THRESHOLD_A=0.003
  THRESHOLD_B=0.005
  WATCH_DURATION=5
  TRIGGER_SLOPE=0.002
  SILENCE_PERIOD=30
  ```

### 验证 GoldClaw 独立运行

- [x] **Step 1: 启动引擎，确认金价获取正常**
  > 验证通过：XAU $4729.90
  ```bash
  python main.py
  ```
  期望日志：`[tick] XAU $xxxx.xx, state=IDLE`
  看到 tick 日志后 Ctrl+C 关闭

- [x] **Step 2: 确认 state_for_openclaw.json 已生成**
  ```bash
  cat data/state_for_openclaw.json | python -m json.tool
  ```
  期望：JSON 含 `system`、`investors`（A 和 B）、`warnings`

- [x] **Step 3: 手动模拟 OpenClaw 开仓指令**
  ```bash
  cat > data/orders_from_openclaw.json << 'EOF'
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
  EOF
  ```

- [x] **Step 4: 重启引擎，确认指令被执行**
  ```bash
  python main.py
  ```
  期望日志：`Processing orders from OpenClaw: 2 instructions`
  等 tick 完成后 Ctrl+C

- [x] **Step 5: 确认数据库已更新**
  ```bash
  sqlite3 data/goldclaw.db "SELECT investor_id, current_action, margin_committed FROM investor_state"
  ```
  期望：A 的 action 为 `cfd_long`，margin_committed > 0

- [x] **Step 6: 确认 trade_history 有记录**
  ```bash
  sqlite3 data/goldclaw.db "SELECT investor_id, action, gold_price FROM trade_history ORDER BY id DESC LIMIT 3"
  ```
  期望：至少有 A 的 `cfd_long` 记录

- [x] **Step 7: 确认 orders 文件被重命名**
  ```bash
  ls data/orders_processed_*.json
  ```
  期望：存在一个 processed 文件

- [x] **Step 8: 手动模拟平仓**
  ```bash
  cat > data/orders_from_openclaw.json << 'EOF'
  {
    "timestamp": "2026-04-09T12:05:00Z",
    "instructions": [
      {"investor": "A", "action": "close"},
      {"investor": "B", "action": "idle"}
    ]
  }
  EOF
  python main.py
  ```
  期望日志：A 平仓，trade_history 新增 `close` 记录

### 配置 Bridge（可选）

- [x] **Step 9: 启动 Bridge**（端口 8088）
  ```bash
  python openclaw_bridge.py 8088
  ```
  ```bash
  # 另开一个终端
  python openclaw_bridge.py
  ```
  期望：`Uvicorn running on http://0.0.0.0:8088`

- [x] **Step 10: 配置 .env 启用门铃**
  ```
  OPENCLAW_BRIDGE_URL=http://localhost:8088/emergency
  ```

- [x] **Step 11: 测试门铃**
  ```bash
  curl -X POST http://localhost:8088/emergency \
    -H "Content-Type: application/json" \
    -d '{"event":"state_trigger","gold_price":4800,"message":"test"}'
  ```
  期望：返回 `{"status": "received", ...}`

- [x] **Step 12: 确认 bridge_events.jsonl 有记录**
  ```bash
  cat data/bridge_events.jsonl
  ```

- [x] **Step 13: 配置 OPENCLAW_TRIGGER_CMD**
  已配置为 `openclaw agent --deliver -m`，消息由 `_trigger_openclaw` 动态拼接。
  验证通过：margin_call 事件 → `[GoldClaw 紧急通知] 事件: margin_call | 投资者: A | 当前金价: $4,580.00`

### 准备 OpenClaw

- [x] **Step 14: 将以下文件提供给 OpenClaw**
  - `RULES.md` — 通信规范（cron job 已配置读取）
  - `data/state_for_openclaw.json` — 示例状态文件

- [x] **Step 15: 确认 OpenClaw 能读写 data/ 目录**
  同机运行，路径 `/Users/orcastt/Code project/GoldClaw/data/`

- [x] **Step 16: OpenClaw 实现 4 步流程**
  cron job 已配置：`0 */3 * * *`（每 3 小时），读取状态 + RULES.md → 决策 → 写 orders 文件

### 端到端联调

- [x] **Step 17: 启动 GoldClaw + OpenClaw 同时运行**

- [x] **Step 18: OpenClaw 发 idle 指令** → 确认文件通路通

- [x] **Step 19: OpenClaw 发开仓指令**（A 做 cfd_long）→ 确认交易执行
  > 验证通过：A cfd_long @ $4,740, margin=6930, tp=4876, sl=4638

- [x] **Step 20: 等几个 tick** → 确认盈亏跟踪（state_for_openclaw.json 中 nominal_pnl 变化）
  > 验证通过：金价 $4,743.90 时 A nominal_pnl=+$114.04

- [x] **Step 21: OpenClaw 发 close** → 确认平仓 + trade_history 记录
  > 验证通过：A 平仓净赚 +$235.67，cash=$10,165.67

- [x] **Step 22: OpenClaw 发非法指令**（A 做 sgln_long）→ 确认被拦截，violations 表有记录
  > 验证通过：violations 表记录 "Investor A cannot sgln_long"，A 状态未变

- [x] **Step 23: 检查下次状态文件 warnings 字段** → 确认 OpenClaw 能看到前置警告
  > 验证通过：state_for_openclaw.json warnings 数组包含违规详情

---

## 一、联调验证检查点

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

## 二、常见问题排查

| 问题 | 排查 |
|------|------|
| 金价获取失败 | 检查网络，确认 `https://api.gold-api.com/price/XAU` 可访问 |
| 指令没被执行 | 确认文件名是 `orders_from_openclaw.json`（不是别的） |
| 指令被拒收 | 检查 violations 表，看具体错误原因 |
| Bridge 连不上 | 确认 bridge 已启动，端口和 URL 一致 |
| OpenClaw 读不到状态 | 确认 `data/` 路径对 OpenClaw 可读 |
| 指令过期被丢弃 | timestamp 超过 30 分钟会被丢弃，确保用当前 UTC 时间 |

---

## 三、文件速查

| 文件 | 用途 | 谁读写 |
|------|------|--------|
| `.env` | GoldClaw 配置 | 你手动编辑 |
| `data/goldclaw.db` | SQLite 真相源 | 仅 GoldClaw |
| `data/state_for_openclaw.json` | 状态报告 | GoldClaw 写，OpenClaw 读 |
| `data/orders_from_openclaw.json` | 投资决策 | OpenClaw 写，GoldClaw 读 |
| `data/orders_processed_*.json` | 已处理的决策 | GoldClaw 重命名 |
| `data/bridge_events.jsonl` | 门铃事件日志 | Bridge 写 |
| `RULES.md` | 通信规范 | OpenClaw 必读 |
| `openclaw_bridge.py` | 门铃接收器 | 你启动 |
