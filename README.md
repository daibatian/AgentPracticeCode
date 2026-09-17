# AI 私人厨师 · 多用户智能体应用

> 上传一张食材照片或一句「今晚吃什么」，智能体完成 **食材识别 → 联网检索菜谱 → 多维打分排序 → 输出带参考图的结构化推荐报告**。

这是一个面向个人的智能菜谱助手：把多步任务编排交给可持久化的 LangGraph 智能体，外面套上自建的多用户账号体系和 Vue3 前端。后端同时托管前端构建产物，单进程即可对外提供服务。

---

## 功能特性

- **多模态对话**：支持上传食材图片，走多模态模型识别食材（图片经浏览器压缩后直传 OSS，不占用服务器带宽）。
- **流式输出**：后端 `StreamingResponse` 逐块吐字，前端用 `ReadableStream` 实时渲染。
- **多用户 · 多会话**：自建账号体系（PBKDF2 加盐哈希 + 服务端会话令牌），会话按 `thread_id` 持久化，接口层校验归属，越权一律 403。
- **个性化口味**：用户可设置称呼、口味、辣度、饮食目标、忌口、偏好菜系，每轮对话自动注入系统提示词。
- **联网检索**：接入 Tavily 联网搜索，工具结果做结构化压缩后再进上下文。
- **上下文治理**：历史 token 超过阈值自动摘要，只保留最近若干轮，兼顾成本与连贯性。
- **模型高可用**：主模型 + 备用模型链全部配置化，额度耗尽 / 限流 / 模型不可用时自动降级。
- **额度与限流**：每用户每周 100 万 token 额度（每周一 0 点重置）+ 每分钟请求次数限流，防止公开服务被刷额度；顶栏实时显示本周剩余额度（用尽时变红），个人中心里可看本周用量详情。
- **管理后台**：独立的管理端页面挂在 `/admin`，分「用户管理」和「操作日志」两个页签。用户管理提供列表搜索分页、行内操作（改额度 / 改权限 / 强制下线 / 重置密码 / 删除）和只读详情抽屉；所有管理写操作（含被拒绝的尝试）都会留痕，可在操作日志里按操作类型和结果筛选。列宽可拖拽且默认自动铺满，非管理员登录会看到明确提示。
- **历史回放**：侧边栏按最后活跃时间列出会话，可随时回看、切换、删除。

## 技术栈

| 层次 | 选型 |
|---|---|
| 语言 / 包管理 | Python 3.12、uv |
| Web 框架 | FastAPI + Uvicorn |
| 智能体 | LangChain（`create_agent`）、LangGraph（`AsyncPostgresSaver`）、中间件（`dynamic_prompt`、`SummarizationMiddleware`） |
| 模型 / 工具 | 通义千问（DashScope，OpenAI 兼容协议）、Tavily 联网搜索 |
| 存储 | PostgreSQL + psycopg3（异步连接池） |
| 对象存储 | 阿里云 OSS（服务端预签名，浏览器直传） |
| 前端 | Vue 3 + Vite + TypeScript + Tailwind CSS 4、markdown-it |
| 部署 | Linux + systemd，单端口托管 API 与前端静态资源 |

## 系统架构

```
浏览器（Vue3 SPA，由后端托管静态资源）
   │  fetch + ReadableStream（纯文本流）
   ▼
FastAPI（app/main.py：连接池 / checkpointer / agent 池在 lifespan 内建一次并复用）
   ├── /api/v1/auth      注册 / 登录 / 登出 / 当前用户
   ├── /api/v1/chat      流式对话（含模型降级）、历史消息、会话列表
   ├── /api/v1/profile   用户资料与口味偏好、修改密码
   └── /api/v1/oss       OSS 预签名（对象名由服务端生成）
   │
   ▼
LangGraph 智能体（模型 + 工具 + 中间件）
   ├── web_search              Tavily 搜索，结果压缩为「标题 + 链接 + 摘要 + 参考图」
   ├── dynamic_prompt          每轮注入当前用户的称呼与口味偏好
   └── SummarizationMiddleware 上下文超阈值自动摘要
   │
   ▼
PostgreSQL
   ├── checkpoints / checkpoint_blobs / checkpoint_writes  ← LangGraph 自动建表，存对话状态
   └── app_users / app_sessions / app_threads               ← 业务表，存账号、令牌、会话归属
```

## 目录结构

```
.
├── app/
│   ├── main.py                    入口：事件循环、连接池、checkpointer、agent 池、路由挂载、静态托管
│   ├── agents/
│   │   └── personal_chief.py      模型工厂、Tavily 工具与结果压缩、动态提示词、摘要中间件、agent 池
│   ├── api/
│   │   ├── deps.py                令牌解析与当前用户依赖
│   │   └── v1/
│   │       ├── chat.py            流式对话（模型降级循环）、历史消息、会话列表
│   │       ├── auth.py            注册 / 登录 / 登出 / me
│   │       ├── profile.py         资料与口味偏好、修改密码
│   │       ├── quota.py           本周额度与用量查询
│   │       └── oss.py             OSS 预签名 URL
│   ├── common/
│   │   ├── db.py                  业务表建表与平滑迁移（add column if not exists）
│   │   ├── quota.py               每周额度、限流器、用量累加（含 app_usage_daily 建表）
│   │   ├── llm.py                 模型清单与「该不该降级」的判断
│   │   ├── preferences.py         口味偏好 → 提示词文本
│   │   ├── security.py            PBKDF2 密码哈希、会话令牌
│   │   └── logger.py              日志配置
│   ├── models/schemas.py          请求 / 响应模型
│   ├── static/                    前端构建产物（由 FastAPI 托管）
│   └── static_admin/              管理端构建产物（挂在 /admin）
├── admin/                         管理端前端源码（Vue3 + Vite，构建直接输出到 app/static_admin）
├── langgraph.json                 注册 chief_agent，供 `langgraph dev` 调试
├── lc-course.py / lc-course.ipynb 学习阶段的脚本，不属于运行链路
├── src/                           学习阶段的示例代码，不属于运行链路
└── pyproject.toml
```

## 快速开始

### 环境要求

- Python 3.12、[uv](https://docs.astral.sh/uv/)
- PostgreSQL（本地或云数据库均可）
- 通义千问 API Key、Tavily API Key；如需上传图片再准备阿里云 OSS

### 1. 后端

```bash
uv sync                       # 安装依赖（首次或依赖变更时）
cp .env.example .env          # 按「配置说明」填好各项
uv run python -m app.main     # 启动，默认 http://127.0.0.1:8001
```

> Windows PowerShell 下 `cp` 换成 `Copy-Item`，`cp -r` 换成 `Copy-Item -Recurse`。

启动后直接访问 `http://127.0.0.1:8001` 即可使用（后端同时托管已构建的前端）。
本地调试接口文档时，在 `.env` 里把 `DOCS_ENABLED` 设为 `true`，`/docs` 与 `/redoc` 才会开放。

调试智能体本身（不经过 Web 层）：

```bash
langgraph dev                  # 读取 langgraph.json，注册 chief_agent
```

### 2. 前端

前端源码独立于本仓库维护，开发模式热更新：

```bash
npm install
npm run dev                   # http://localhost:5173
```

前后端分开跑时，在前端目录建 `.env.local` 指定后端地址：

```
VITE_API_BASE=http://localhost:8001
```

### 3. 构建前端并交给后端托管

```bash
npm run build                 # 产物在 dist/
cp -r dist/* <后端目录>/app/static/
```

静态资源是每次请求读磁盘，只更新前端**不需要重启**后端。

### 4. 管理端（/admin）

管理端源码在后端仓库的 `admin/` 目录下，构建产物直接写进 `app/static_admin/`（省掉手工拷贝，也不会堆历史产物）：

```bash
cd admin
npm install
npm run build                 # 产物落到 ../app/static_admin
```

后端启动时会把它挂在 `/admin`（访问 `/admin` 会自动跳到 `/admin/`）。本地开发时可以单独跑 `npm run dev`（端口 5174），用 `VITE_API_BASE` 指到后端。

管理端用的是同一套登录接口，但**令牌单独存储**（`chef_admin_token`），所以在同一个浏览器里，管理端和用户端不会互相把对方挤下线。

列表的列宽默认按可用宽度自动铺满整行；拖动表头分隔线可以自行调整，**一旦拖过就进入手动模式**（宽度固定成你拖的样子，窗口变化不再自动改），点工具栏的「重置列宽」回到自动铺满。自己的账号在「操作」列里的敏感按钮会自动禁用，避免把自己踢下线或改掉自己的密码。

「操作日志」记录每一次管理写操作：谁、什么时候、对谁、做了什么、结果如何（成功 / 被拒绝）以及来源 IP。管理员和对象的名字会额外存一份快照，所以即使账号被删掉，历史日志依然看得懂。**被拒绝的尝试也会记录**——比如"有人试图重置自己的密码"。

## 配置说明（.env）

`.env` 不入库，需自行创建。变量如下（值仅为示例，请替换为你自己的）：

| 变量 | 说明 | 示例 |
|---|---|---|
| `MODEL_NAME` | 主模型 | `qwen3.8-flash` |
| `MODEL_FALLBACKS` | 备用模型链，逗号分隔，按顺序降级 | `qwen3.7-plus,qwen3.7-flash,qwen3.7-max` |
| `CONTEXT_MAX_TOKENS` | 历史估算超过该值触发自动摘要 | `12000` |
| `CONTEXT_KEEP_MESSAGES` | 摘要后保留最近多少条消息 | `8` |
| `POSTGRES_URI` | 数据库连接串 | `postgresql://user:password@127.0.0.1:5432/dbname?sslmode=disable` |
| `DASHSCOPE_API_KEY` | 通义千问 API Key | — |
| `DASHSCOPE_BASE_URL` | 通义千问 OpenAI 兼容地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `TAVILY_API_KEY` | Tavily 联网搜索 Key | — |
| `OSS_ACCESS_KEY_ID` / `OSS_ACCESS_KEY_SECRET` | OSS 访问凭证（建议用 RAM 子账号，只授权单桶） | — |
| `OSS_BUCKET` / `OSS_ENDPOINT` | OSS 桶名与地域域名 | `my-bucket` / `oss-cn-beijing.aliyuncs.com` |
| `REGISTRATION_ENABLED` | 注册开关，`false` 时只有已有账号能登录 | `false` |
| `DOCS_ENABLED` | 是否开放 `/docs`、`/redoc`、`/openapi.json` | `false` |
| `DEFAULT_WEEKLY_TOKEN_QUOTA` | 新用户的默认每周 token 额度（0 = 不限） | `1000000` |
| `RATE_LIMIT_PER_MINUTE` | 每个用户每分钟最多发起几次对话（0 = 不限） | `6` |
| `QUOTA_TIMEZONE` | 额度按哪个时区的自然周重置（周一 0 点） | `Asia/Shanghai` |
| `LANGSMITH_API_KEY` / `LANGSMITH_TRACING` / `LANGSMITH_PROJECT` | 可选的链路追踪 | `false` |
| `HOST` / `PORT` | 监听地址与端口 | `127.0.0.1` / `8001` |

> 说明：历史版本的学习脚本会用到 `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL`，当前运行链路走的是通义千问，这两项可以留空。

## 接口一览

所有接口前缀均为 `/api/v1`。「需登录」表示必须携带 `Authorization: Bearer <token>`。

| 方法 | 路径 | 说明 | 需登录 |
|---|---|---|---|
| POST | `/auth/register` | 注册（`REGISTRATION_ENABLED=false` 时返回 403） | 否 |
| POST | `/auth/login` | 登录，返回令牌（有效期 30 天） | 否 |
| GET | `/auth/me` | 当前用户 | 是 |
| POST | `/auth/logout` | 登出（服务端删除令牌） | 是 |
| POST | `/chat/stream` | 流式对话，返回纯文本流（非 SSE） | 是 |
| GET | `/chat/messages` | 读取某个会话的历史消息 | 是 |
| DELETE | `/chat/messages` | 删除某个会话的历史 | 是 |
| GET | `/chat/threads` | 当前用户的会话列表（最近活跃在前） | 是 |
| GET | `/profile` | 读取资料与口味偏好 | 是 |
| PUT | `/profile` | 更新资料与口味偏好（只更新传入字段） | 是 |
| POST | `/profile/password` | 修改密码 | 是 |
| GET | `/quota` | 本周额度与用量（额度、已用、剩余、请求数、下次重置时间） | 是 |
| GET | `/oss/presign` | 获取图片上传的预签名 URL | 是 |

管理端接口（全部需要管理员身份，非管理员返回 403）：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/admin/users` | 用户列表（`q` 搜索、`page`/`size` 分页，带本周用量与会话/设备数） |
| GET | `/admin/users/{id}` | 用户详情（资料、口味偏好、本周额度与用量、最后活跃） |
| PATCH | `/admin/users/{id}` | 改权限 / 改额度覆盖（额度传 `null` = 恢复全局默认） |
| POST | `/admin/users/{id}/logout-all` | 强制下线（清除该用户所有登录令牌） |
| POST | `/admin/users/{id}/reset-password` | 重置密码，返回一次性临时密码 |
| DELETE | `/admin/users/{id}` | 删除用户（连带会话、对话状态、令牌与用量记录） |
| GET | `/admin/logs` | 操作日志（`action`、`result`、`admin_username`、`target_user_id` 过滤 + 分页） |

## 关键设计

### 1. 会话持久化与多用户隔离

`AsyncPostgresSaver` + 异步连接池在应用 `lifespan` 里建**一次**并全程复用，`setup()` 幂等建表；对话内容由 LangGraph 的 `checkpoint_*` 表承载。业务侧另建三张表：`app_users`（账号）、`app_sessions`（服务端会话令牌）、`app_threads`（会话归属）。所有会话相关接口先校验归属，越权返回 403。

### 2. 上下文治理

- **工具结果压缩**：Tavily 原始 JSON 含大量字段名、评分与长正文，压缩为「标题 + 链接 + 摘要 + 参考图」，只保留模型真正需要的部分。
- **自动摘要**：`SummarizationMiddleware` 在历史超过 `CONTEXT_MAX_TOKENS` 时生成摘要，并保留最近 `CONTEXT_KEEP_MESSAGES` 条消息。

### 3. 模型降级

模型名与备用链全部来自环境变量。区分「可降级」与「不可降级」异常：额度耗尽、限流、服务端 5xx、模型不存在等换下一个模型重试；请求本身格式错误则直接失败。**只有当本次回复还没吐出任何字符时才会降级**，避免内容重复。

### 4. 动态提示词

`dynamic_prompt` 中间件每轮把「称呼 + 口味偏好」拼进系统提示词，同一套 Agent 即可输出个性化结果；用户没设置偏好时，提示词与未接入该功能时完全一致。

### 5. 图片直传

服务端只签发预签名 URL，浏览器直接 PUT 到 OSS，不经服务器中转。对象名由服务端生成（`u<用户id>/<随机名>.<扩展名>`）并校验扩展名白名单，客户端传入的文件名不作为 key 使用。

### 6. 前端细节

- Markdown 图片统一加 `referrerpolicy="no-referrer"`：部分图床带 Referer 会返回 403，导致参考图不显示。
- 头像在上传前用 Canvas 裁剪压缩为 128×128。
- 流式输出用 `requestAnimationFrame` 节流滚动，避免页面抖动。

### 7. 配额与限流

- **额度按 token 计**，不按对话次数：实测一次文字提问约 3.6k token、一次图片提问约 22k token，按次数限制会差 6 倍。
- **按自然周重置（周一 0 点）、时区可配**：服务器时区通常是 UTC，不配 `QUOTA_TIMEZONE` 会把重置时刻挪到北京时间周二早上 8 点。
- **用量按天存、按周汇总**：`app_usage_daily` 每天一行（后台看趋势），配额判断时求和本周的行——既能按周限额，又不丢日粒度。
- **默认额度全局配置 + 按用户覆盖**：`DEFAULT_WEEKLY_TOKEN_QUOTA` 决定所有新用户的额度，不必逐个分配；要给某个用户单独加量时，写 `app_users.weekly_token_quota` 即可（NULL = 用全局默认）。
- **限流是单进程内存滑动窗口**，主要挡脚本式的突发请求；多实例部署时每个实例各限一份，要全局精确需换成 Redis 之类的共享计数。
- 用量在**整个请求结束时**统一落库（正常结束 / 报错 / 客户端中途断开都会记），避免"断开就不计费"被绕过。

## 实测数据

以下数据在开发过程中实测，可作为性能调优的参考基线：

| 场景 | 结果 |
|---|---|
| 纯文字提问（1 次联网搜索） | 输入 2,678 + 输出 882 ≈ **3,600 token** |
| 图片提问（5 次联网搜索） | 输入 19,018 + 输出 2,984 ≈ **22,000 token**（输入占 86%） |
| 工具结果压缩 | 单次搜索 7,259 字符 → 2,462 字符，**降低 66%** |
| 自动摘要 | 8 条消息 / 11,403 字符 → 1 条摘要（3,548 字符）+ 最近若干轮 |

输入占比高的原因是：Agent 每调用一次工具，都要把「系统提示 + 全部历史 + 所有工具结果」重新发给模型一次，因此工具结果压缩与历史摘要对成本影响最大。

## 部署

以 Linux 服务器 + systemd 为例：

```bash
# 服务器上
cd /opt/chef
git pull
uv sync --frozen              # 仅依赖变更时需要
systemctl restart chef        # 服务文件里用 EnvironmentFile 指向 /opt/chef/.env
systemctl status chef --no-pager
```

服务启动命令为 `uv run python -m app.main`，监听 `8001`；数据库建议只走内网（`127.0.0.1` 或云数据库内网地址），**不要对公网开放 5432**。

## 安全说明

已实现：

- 密码用 PBKDF2-SHA256（20 万次迭代、随机盐）哈希存储，校验时用常数时间比较。
- 会话令牌由服务端随机生成并入库，登出即失效；登录失败不区分「用户不存在」与「密码错误」。
- 会话、消息、资料接口均校验归属，越权返回 403。
- 图片上传需登录，对象名服务端生成、扩展名白名单校验。
- 接口文档默认关闭（`DOCS_ENABLED`）；注册可一键关闭（`REGISTRATION_ENABLED`）。
- 每用户每周 token 额度 + 每分钟请求数限流，额度可在 `app_users.weekly_token_quota` 按用户覆盖。
- 管理接口要求 `is_admin`（未登录 401、非管理员 403）；管理员名单由 `.env` 的 `ADMIN_USERNAMES` 在启动时补齐，只提升不降级，保证不会把自己锁在后台外面。
- 管理写操作全部落审计日志（`app_admin_logs`），含被拒绝的尝试；日志里不记敏感内容（如临时密码）。
- 数据库连接串只从环境变量读取，代码与仓库中不含明文凭据。

部署到公网前建议补充：

- 收紧 CORS（当前为 `allow_origins=["*"]`），改为具体域名；
- 配置域名 + HTTPS（国内服务器需先完成 ICP 备案）；
- 定期轮换密钥，数据库与 OSS 使用独立的最小权限账号；
- 把 `DEFAULT_WEEKLY_TOKEN_QUOTA` 调成符合自己成本预算的值（示例值 100 万 token/周）。

## Roadmap

- [x] 每用户每周配额与限流（防止公开服务被刷额度）
- [x] 管理后台：用户管理（列表 / 额度 / 权限 / 强制下线 / 重置密码 / 删除）
- [x] 管理后台：操作审计日志（写操作留痕、可筛选）
- [ ] 管理后台：会话管理、模型配置、用量报表
- [ ] 会话重命名、置顶、搜索；回复点赞点踩反馈闭环
- [ ] 域名 + HTTPS + 监控告警
- [ ] 数据库自动备份与日志轮转

## 说明

- `lc-course.py`、`lc-course.ipynb` 与 `src/` 是学习和调试阶段的记录，不属于线上运行链路。
- 数据来源依赖第三方搜索与模型服务，菜谱内容仅供参考。
