# project_state.md — GoldClaw 项目当前状态

> 本文档在任何时候打开，都能准确反映项目此刻的真实状态。
> 每次开新对话前让 AI 读这份文件，确保它的世界观是准的。

---

## 当前阶段

**v0.4.0 已发布** — 核心引擎 + Dashboard + 原生窗口 + DMG 打包 + 备份 + i18n + 资产曲线全部完成。
GitHub Release: https://github.com/chuhengtantt/GoldClaw/releases/tag/v0.4.0

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
### 切片 12: 数据库备份系统 ✅
- `internal/db/backup.py`：WAL checkpoint + 文件复制 + 滚动保留（最多 10 份）
- 自动备份：启动时 + 关闭时
- 手动备份：Dashboard 备份按钮（创建/列出/恢复）
- 备份文件命名：`goldclaw_YYYYMMDD_HHMMSS.db`
- 备份目录：`~/GoldClaw/backup/`
- API 端点：`GET /api/backups`、`POST /api/backup`、`POST /api/backup/restore`
### 切片 13: 中英文语言切换 ✅
- Dashboard i18n 系统：`data-i18n` HTML 属性 + JS 翻译字典
- 支持中文/英文一键切换，状态持久化到 localStorage
- 所有 UI 文本可翻译（标题、标签、按钮、状态名）
- 语言切换按钮在 Header 右侧
### 切片 14: 投资者资产曲线图 ✅
- A/B 双线折线图（紫色=A #8B5CF6，蓝色=B #3B82F6）
- 决策标注点（LONG/SHORT/CLOSE/SGLN 标签）
- 日/周/月视图切换
- Chart.js 自定义 plugin 绘制决策标签
- 数据源：`investor_snapshots` + `trade_history` UNION 查询
- API 端点：`GET /api/asset-history?range=day|week|month`
### 切片 15: 每 tick 资产快照 ✅
- 新增 `investor_snapshots` 表（每 tick INSERT 投资者总资产 + 持仓动作）
- `get_asset_history()` 合并 investor_snapshots + trade_history，按时间正序
- Dashboard 布局改为左列上下结构：金价图（上）+ 资产曲线图（下）+ 右侧投资者卡片
- 金价图与资产图之间可拖拽垂直 resize handle

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
| `investor_snapshots` | 投资者资产快照（每 tick 记录） | INSERT Only |

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
| GET | `/api/asset-history?range=day\|week\|month` | 投资者资产历史曲线 |
| GET | `/api/backups` | 列出备份文件 |
| POST | `/api/backup` | 手动创建备份 |
| POST | `/api/backup/restore` | 从备份恢复数据库 |
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
│   │   ├── repository.py            # InvestorRepository + DashboardRepository
│   │   └── backup.py                # 备份/恢复/滚动保留
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
