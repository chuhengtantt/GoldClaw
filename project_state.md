# project_state.md — GoldClaw 项目当前状态

> 本文档在任何时候打开，都能准确反映项目此刻的真实状态。
> 每次开新对话前让 AI 读这份文件，确保它的世界观是准的。

---

## 当前阶段

**v0.2.0 已发布** — 核心引擎 + Dashboard + 原生窗口 + DMG 打包全部完成。
GitHub Release: https://github.com/chuhengtantt/GoldClaw/releases/tag/v0.2.0

### 当前运行状态
- **GoldClaw.app**: macOS 原生应用，pywebview 窗口（端口 8089）
- **Dashboard**: http://localhost:8089/dashboard/（原生窗口自动打开）
- **Bridge**: 已集成到 dashboard_api.py（`POST /emergency`，端口 8089）
- **数据目录**: `/Users/orcastt/GoldClaw/data/`（.app 打包后自动使用此路径）
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
### 切片 8: 集成测试（25 tests） ✅
### 切片 9: OpenClaw 端到端联调（23 步） ✅
### 切片 10: Dashboard 控制面板 ✅
- 金价折线图（Chart.js，红涨绿跌，日/周/月视图）
- 投资者 A/B 持仓明细 + 交易记录（分页）
- OpenClaw 通讯监控（日/周/月视图）
- 运行时参数配置（调度间隔、状态机阈值，Dashboard UI 修改）
- 日志管理（清理 price_ticks / comm_log）
- 两页 Tab 布局：资产页 + 通讯状态
- 可拖拽面板宽度调整
### 切片 11: macOS 应用打包 ✅
- pywebview 原生窗口（替代浏览器）
- PyInstaller .app bundle
- DMG 安装包（hdiutil，含 Applications 快捷方式）
- 应用图标（金色爪痕 + 暗色背景）
- 数据目录 ~/GoldClaw/（.app 启动时自动使用）

---

## OpenClaw 接入指南

详见 `RULES.md`。快速参考：

### 数据文件位置（.app 打包后）

| 文件 | 路径 |
|------|------|
| 状态文件 | `/Users/orcastt/GoldClaw/data/state_for_openclaw.json` |
| 决策文件 | `/Users/orcastt/GoldClaw/data/orders_from_openclaw.json` |
| 通讯规范 | `/Users/orcastt/GoldClaw/RULES.md` |
| SQLite 数据库 | `/Users/orcastt/GoldClaw/data/goldclaw.db`（OpenClaw 不碰） |

### 权限速查

| Action | 投资者A | 投资者B |
|--------|---------|---------|
| `cfd_long` | ✅ | ❌ |
| `cfd_short` | ✅ | ✅ |
| `sgln_long` | ❌ | ✅ |
| `hold` | ✅ | ✅ |
| `idle` | ✅ | ✅ |
| `close` | ✅ | ✅ |

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
| `runtime_config` | 运行时参数配置（Dashboard 可修改） | UPSERT |

---

## Dashboard API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/dashboard/` | Dashboard 主页 |
| GET | `/api/prices?range=day\|week\|month` | 金价历史 |
| GET | `/api/prices/latest` | 最新金价 |
| GET | `/api/investors` | 投资者状态 |
| GET | `/api/investors/{id}/trades` | 交易记录（分页） |
| GET | `/api/comm?page=&size=` | 通讯日志 |
| GET | `/api/comm/summary?range=week\|month` | 通讯汇总 |
| GET | `/api/system` | 系统状态 |
| GET | `/api/logs/stats` | 日志统计 |
| DELETE | `/api/logs/price_ticks?before=` | 清理金价记录 |
| DELETE | `/api/logs/comm_log?before=` | 清理通讯日志 |
| GET | `/api/config` | 获取运行时参数 |
| PATCH | `/api/config` | 修改运行时参数 |
| POST | `/api/config/reset` | 恢复默认参数 |
| POST | `/emergency` | 紧急通知（Bridge 端点） |
| GET | `/health` | 健康检查 |

---

## 待开发

- **指令过期检测 (F5)**: PRD 中定义但未实现，当前不检查 timestamp TTL
- **门铃后轮询**: Bridge 触发后每 30s 检查 orders 文件（最多 3 分钟），未实现
- **历史回测 (F23)**: 导入历史金价数据进行策略回测
- **社媒运营 (F21/F22)**: 自动生成交易摘要发布到社交平台

---

## 运行配置

```bash
# 激活虚拟环境
source .venv/bin/activate

# 开发模式（Engine + Dashboard + 浏览器）
python run.py

# macOS App 模式（原生窗口）
python app_main.py

# 运行测试
pytest tests/ -v

# 构建 DMG
bash build_dmg.sh

# 构建源码包
bash build.sh
```

---

## 文件清单（已实现）

```
GoldClaw/
├── app_main.py                      # macOS App 入口（pywebview 原生窗口）
├── run.py                           # CLI 入口（Engine + Dashboard）
├── main.py                          # CLI 入口（仅 Engine）
├── openclaw_bridge.py               # 门铃接收器（已集成到 dashboard_api）
├── dashboard_api.py                 # Dashboard + Bridge REST API（端口 8089）
├── build_dmg.sh                     # DMG 构建脚本
├── build.sh                         # Tarball 构建脚本
├── PRD.md                           # 产品需求
├── ARCH.md                          # 技术架构
├── RULES.md                         # OpenClaw 通信规范
├── project_state.md                 # 本文件
├── README.md                        # 项目说明
├── requirements.txt                 # 运行时依赖
├── requirements-dev.txt             # 开发依赖
├── .env / .env.example              # 环境配置
├── .gitignore
├── dashboard/                       # Dashboard 前端
│   ├── index.html
│   └── static/
│       ├── style.css                # Revolut 风格设计系统
│       ├── app.js                   # Chart.js + 交互逻辑
│       └── app_icon.icns            # 应用图标
├── docs/
│   └── dashboard_dev_plan.md
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
    └── test_integration.py          # 25 tests
```

---

## 已知问题

- **F5 指令过期检测未实现**: PRD 定义了 30 分钟 TTL，但代码未检查 timestamp。当前所有指令都会被执行（不影响安全，因为 Pydantic 校验仍在）。
- **15 分钟延迟**: OpenClaw 写入 orders 文件后，GoldClaw 最长需要等 15 分钟（IDLE tick 间隔）才捡起执行。
