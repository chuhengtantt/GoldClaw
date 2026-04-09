# ARCH.md — GoldClaw 技术架构与工程约束

> 本文档定义技术决策、工程规范和开发纪律。
> 用户看不到这些内容，但它们决定了系统怎么建。

---

## 1. 技术栈

| 层 | 选型 | 理由 |
|----|------|------|
| 语言 | Python 3.11+ | 标准库内置 sqlite3，生态成熟 |
| 数据库 | SQLite (WAL 模式) | 单文件、零配置、ACID 事务、防 LLM 误写 |
| 调度 | APScheduler | 轻量定时任务，无需 cron |
| HTTP 客户端 | httpx | 异步就绪、超时控制精细 |
| 数据校验 | Pydantic v2 | 严格 Schema 校验 + 幻觉检测 |
| 配置管理 | pydantic-settings + .env | 类型安全的环境变量 |
| Bridge / Dashboard | FastAPI + uvicorn | 门铃接收器 + Dashboard REST API（端口 8088） |
| 版本管理 | Git | 代码快照、回退、协作 |

不用的：
- **不用 MySQL/PostgreSQL**: 本地单文件足够，不需要数据库服务
- **不用 Redis**: 无缓存需求
- **不用 Docker**: 本地单进程运行，不需要容器化

---

## 2. 目录结构

```
GoldClaw/
├── PRD.md                           # 产品需求（用户能验收的功能）
├── ARCH.md                          # 技术架构与工程约束（本文件）
├── project_state.md                 # 项目当前状态（进度、bug、下一步）
├── main.py                          # 入口：启动调度器
├── openclaw_bridge.py               # 门铃接收器（FastAPI，端口 8088）
├── dashboard_api.py                 # Dashboard REST API（FastAPI）
├── requirements.txt                 # 依赖
├── .env                             # 真实配置（不提交 Git）
├── .env.example                     # 配置模板（提交 Git）
├── .gitignore
│
├── dashboard/                       # Dashboard 前端（开发中）
│   ├── index.html
│   └── static/
│
├── docs/                            # 开发文档
│   └── dashboard_dev_plan.md
│
├── config/                          # 配置层
│   ├── __init__.py
│   ├── settings.py                  # pydantic-settings
│   └── defaults.py                  # 默认常量
│
├── profiles/                        # 投资者画像（YAML，未来扩展 C/D/E 加文件即可）
│   ├── investor_a.yaml
│   └── investor_b.yaml
│
├── reference/                       # AI 照着写的标准样本
│   ├── coding_style.py              # 代码风格参考
│   ├── error_handling.py            # 错误处理模式
│   └── db_patterns.py               # 数据库操作模式
│
├── app/                             # 应用层（编排）
│   ├── __init__.py
│   ├── scheduler.py                 # APScheduler 调度
│   └── engine.py                    # 主引擎
│
├── internal/                        # 业务逻辑层
│   ├── __init__.py
│   ├── state_machine/               # 状态机（IDLE/WATCH/TRIGGER）
│   │   ├── __init__.py
│   │   ├── machine.py
│   │   └── states.py
│   ├── price/                       # 金价模块
│   │   ├── __init__.py
│   │   ├── fetcher.py
│   │   ├── history.py
│   │   └── volatility.py
│   ├── investor/                    # 投资者模块
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── investor_a.py
│   │   ├── investor_b.py
│   │   └── pnl.py                   # 纯函数盈亏计算
│   ├── db/                          # 数据库层
│   │   ├── __init__.py
│   │   ├── connection.py            # SQLite 连接（WAL 模式）
│   │   ├── migrations.py            # 建表/迁移
│   │   └── repository.py            # 数据访问层（InvestorRepository + DashboardRepository）
│   ├── exchange/                    # 通信层（信箱 + 门铃）
│   │   ├── __init__.py
│   │   ├── schema.py                # Pydantic Schema（信箱/门铃/指令）
│   │   ├── webhook_client.py        # 信箱文件交换 + 门铃 HTTP POST
│   │   └── validator.py             # 指令校验 + 幻觉检测 + 耻辱柱
│   └── exception/                   # 异常处理
│       ├── __init__.py
│       ├── errors.py
│       └── handler.py
│
├── data/                            # 运行时数据（gitignored）
│   ├── goldclaw.db                  # SQLite 数据库
│   ├── state_for_openclaw.json      # 信箱输出（Python → OpenClaw）
│   └── orders_from_openclaw.json    # 信箱输入（OpenClaw → Python）
│
└── tests/                           # 测试
    ├── __init__.py
    ├── test_pnl_calculations.py
    ├── test_state_machine.py
    ├── test_schema_validation.py
    ├── test_investor_a.py
    └── test_investor_b.py
```

---

## 3. 工程约束

### 3.1 文件大小上限：300 行

- 单个文件不超过 300 行
- 快到上限时拆分：把某个功能抽出去，新建独立文件
- 每个文件执行单一职责

### 3.2 数据库安全

- **SQLite WAL 模式**: 所有写操作在事务中完成
- **事务流程**: `BEGIN → UPDATE/INSERT → COMMIT`，异常自动 `ROLLBACK`
- **Pydantic 校验层**: OpenClaw 的决策文件先过 Pydantic 校验，通过才写 SQLite
- **幻觉检测**: 交易前后 total_assets 变化超 50% 则 ROLLBACK
- **Python 是唯一 DBA**: OpenClaw 永远不能直接操作 SQLite

### 3.3 配置安全

- 真实配置存在 `.env` 文件中，不提交 Git
- `.env.example` 只写变量名不写值，可以安全提交
- `.gitignore` 包含 `.env` 和 `data/`

### 3.4 性能底线

- 单次 tick 执行时间 < 5 秒（含 API 请求）
- SQLite 数据库文件不超过 100MB
- 价格历史保留最近 1000 个 tick（超出自清理）
- trade_history 表保留最近 10000 条（超出可归档）

---

## 4. 开发纪律

### 4.1 小步迭代：端到端切片

每次只做能独立验收的最小功能单位。一个切片必须从数据层一路打通到外部接口：

```
数据库层 → 业务逻辑层 → 通信层 → 外部接口
```

不要先把所有模块搭好再接逻辑——中途无法验收任何东西。

### 4.2 每个切片的标准流程

1. 手动跑一遍，对照 PRD 验收清单逐条检查
2. 跑测试：`pytest tests/`
3. 更新 `project_state.md`
4. `git commit`，写清楚这次做了什么

### 4.3 限制 AI 擅自做主

每次提需求，在结尾加上约束：

> 只修改我点名的文件和范围。不要顺手重构，不要改其他模块，不要动无关逻辑。

### 4.4 每次开新对话的第一条消息

```
先读项目根目录的 project_state.md、PRD.md 和 ARCH.md，了解当前状态，
然后我们来做「具体任务」
```

### 4.5 Git commit 前必做

1. 检查 `project_state.md` 是否需要更新
2. 确认测试通过
3. 确认没有提交 `.env` 或敏感数据

---

## 5. 错误处理规范

### 5.1 科学应对报错：两次无新证据就停

连续两次 AI 的回复没有带出新的错误信息、没有新的运行数据——只是换了一种猜测——必须停下来换策略。

排查步骤：
1. **最小复现**: 缩到最小可触发的输入
2. **加日志**: 在关键位置打印变量值，拿到真实运行时数据
3. **写小测试**: 把错误行为用测试用例固定下来
4. **回退**: `git checkout` 回到上一个稳定点，不要在一个坑里越挖越深

### 5.2 异常处理模式

```python
# reference/error_handling.py 中的标准模式
try:
    with db.transaction():
        result = do_something()
        db.commit()
except SpecificError as e:
    logger.error(f"具体错误: {e}")
    # 具体的恢复策略
except GoldClawError as e:
    logger.error(f"引擎错误: {e}")
    # 通用恢复：延续当前策略
```

---

## 6. 数据库表结构速查

| 表名 | 用途 | 操作模式 |
|------|------|----------|
| `investor_state` | 投资者当前状态 | 每个 tick UPDATE |
| `trade_history` | 交易流水（素材库） | INSERT Only |
| `system_state` | 状态机参数 | UPDATE |
| `violations` | 耻辱柱（LLM 违规记录） | INSERT Only |
| `price_ticks` | 金价 tick 历史（Dashboard 数据源） | INSERT Only |
| `comm_log` | 通讯日志（所有方向的事件） | INSERT Only |

详细字段定义见 PRD.md 第 7 节。

---

## 6.2 通信规范（信箱 + 门铃）

GoldClaw 与 OpenClaw 通过 JSON 文件交换数据（信箱），紧急时通过 HTTP POST 唤醒（门铃）。

| 文件 | 方向 | 写入层 |
|------|------|--------|
| `data/state_for_openclaw.json` | Python → OpenClaw | `internal/exchange/webhook_client.py` |
| `data/orders_from_openclaw.json` | OpenClaw → Python | OpenClaw 侧（不在本项目范围） |

- **写入层**：`internal/exchange/` 是唯一的信箱管理员，其他层不碰 JSON 文件
- **真相源**：SQLite 永远是唯一真相源，JSON 只是从 SQLite 生成的信件副本
- **门铃**：TRIGGER 时 POST 到 `OPENCLAW_BRIDGE_URL`（可选）
- **校验**：所有输入文件经过 Pydantic 校验 + 权限校验 + 幻觉检测

**JSON 格式、字段约束、示例**：见 `RULES.md`。

---

## 7. 依赖清单

```
pydantic>=2.5.0
pydantic-settings>=2.1.0
APScheduler>=3.10.0
httpx>=0.27.0
fastapi>=0.110.0
uvicorn>=0.29.0
pytest>=9.0.0
```

> SQLite 是 Python 标准库内置，无需安装。
