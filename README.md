# 企业级智能客服问答系统

这是一个可增删模块、证据优先、低延迟优先的智能客服基础工程。目前包含可运行的知识库与问答最小闭环，存储和模型默认使用内存实现，便于本地启动；生产端口已经预留。

## 架构约束

- 业务模块通过 `ModuleDefinition` 注册，可使用环境变量独立启停。
- 模块间只依赖公开端口，不跨模块读取内部数据。
- AI 流水线按“缓存 → 检索 → 证据门控 → 生成”执行。
- 证据分数不足时必须拒答，所有有效回答必须返回引用。
- 模型、检索器、缓存均通过协议接口替换。

## 本地启动

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\uvicorn customer_service.main:app --reload --port 8080
```

打开 `http://127.0.0.1:8080/docs`。

```powershell
.venv\Scripts\pytest
```

## 最小演示

先调用 `POST /api/v1/knowledge/documents` 添加知识，再调用 `POST /api/v1/conversations/ask` 提问。健康检查位于 `GET /health`，已启用模块位于 `GET /modules`。

## 接入真实大模型

复制 `.env.example` 为 `.env`，然后配置统一的 OpenAI 兼容网关：

```env
AI_MODEL_PROVIDER=openai-compatible
AI_MODEL_BASE_URL=https://api.deepseek.com
AI_MODEL_API_KEY=你的密钥
AI_MODEL_NAME=deepseek-v4-flash
```

也可以把地址与模型名称替换为通义千问或其他兼容服务。通过 `GET /model-status` 查看当前生效模型；接口不会返回 API Key。模型超时或不可用时，默认直接返回检索到的原始知识内容，避免无依据回答。

## 电商客服链路

系统对问题进行分层处理：

1. 订单状态、物流轨迹、退款进度等动态事实直接查询电商业务模块。
2. 退换货政策、发票规则、商品说明等静态规则进入知识库检索。
3. 只有检索到足够证据后才调用大模型组织语言。
4. 无业务数据、无知识证据时拒答或转人工。

开发环境内置一笔演示订单。订单列表接口为 `GET /api/v1/commerce/customers/{customer_id}/orders`，问答接口支持传入 `customer_id`，响应中的 `answer_type` 可区分 `business_fact`、`knowledge` 和 `refusal`。生产环境应将 `InMemoryCommerceStore` 替换为企业 OMS、ERP、WMS 和售后系统适配器。

## 已实现的客服操作

- 创建会话：`POST /api/v1/conversations`
- 查询会话：`GET /api/v1/conversations`
- 读取消息历史：`GET /api/v1/conversations/{id}/messages`
- 转人工并生成工单：`POST /api/v1/handoffs`
- 查询转人工工单：`GET /api/v1/handoffs`
- 更新工单状态：`PATCH /api/v1/handoffs/{id}`
- 创建、查询、编辑和删除知识：`/api/v1/knowledge/documents`

管理页面已经接通以上接口。知识、会话消息和转人工工单已使用 SQLAlchemy 持久化：本地默认写入 `data/customer_service.db`，Docker 环境默认连接 PostgreSQL。健康检查 `/health` 会同步报告数据库状态。

数据库迁移使用 Alembic：本地执行 `uv run alembic upgrade head`，查看版本使用 `uv run alembic current`。Docker 容器会在 API 启动前自动升级到 `head`。

Redis 用于跨实例问答缓存和固定窗口限流。Docker 默认启用；本地可设置 `REDIS_ENABLED=true`。Redis 故障时自动降级到进程内实现，健康检查会显示 `redis=fallback`。

知识检索采用关键词与向量混合评分，默认权重为 `0.45/0.55`。知识新增或更新时自动生成向量，旧知识在启动时补齐。默认 Hash Embedding 用于开发验证，生产应替换为真实语义嵌入模型和向量索引。

启用真实语义嵌入示例：

```env
EMBEDDING_PROVIDER=openai-compatible
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
EMBEDDING_API_KEY=你的百炼密钥
EMBEDDING_MODEL=text-embedding-v4
EMBEDDING_DIMENSIONS=256
```

切换模型后，启动时会自动重建模型名称或维度不一致的知识向量；上游不可用时降级为本地嵌入。

PostgreSQL 环境中 `VECTOR_STORE_PROVIDER=auto` 会启用 pgvector 数据库侧余弦检索和 HNSW 索引；SQLite 自动使用 JSON 向量。当前 HNSW 基线维度为 256，修改维度必须新增 Alembic 迁移。

工单中心支持排队、受理、解决和关闭状态流转；解决或关闭工单后，关联会话会自动退出“待处理”，数据分析同步更新。

客户中心支持客户档案、会员等级、来源地区、累计订单与消费、客户标签和状态管理。客服工作台右侧客户画像由 `GET /api/v1/customers/{id}` 实时加载，资料更新使用 `PATCH /api/v1/customers/{id}`，所有查询均带租户边界。

## 企业登录与权限

认证默认关闭，配置以下环境变量后启用：

```env
AUTH_ENABLED=true
AUTH_JWT_SECRET=至少32位随机密钥
AUTH_BOOTSTRAP_ADMIN_EMAIL=admin@example.com
AUTH_BOOTSTRAP_ADMIN_PASSWORD=至少8位强密码
AUTH_BOOTSTRAP_ADMIN_NAME=系统管理员
```

启用后访问首页会跳转至中文登录页。系统使用 Argon2 密码哈希、带有效期的 JWT HttpOnly Cookie，并提供 `owner`、`admin`、`editor`、`agent`、`viewer` 五级角色。所有 API 会验证登录身份与 `tenant_id`，知识和客户写操作至少需要编辑权限，审计日志仅管理员可读取。关键写操作自动保存到 `audit_logs`。

## 生产化增强（2026-06-30）

当前版本已经完成真实 OpenAI 兼容 LLM/Embedding 适配器、DashScope `qwen3-rerank` 专业重排、pgvector HNSW、独立 HTTP Mock OMS、登录/RBAC/租户隔离/审计、Prometheus、Grafana、JSON 结构化日志、GitHub Actions 和 Docker Compose 一键启动。

```powershell
docker compose up -d --build
```

- 客服系统：http://127.0.0.1:8080
- Mock OMS：http://127.0.0.1:8090
- Prometheus：http://127.0.0.1:9091
- Grafana：http://127.0.0.1:3001
- 本地演示账号：`admin@example.com` / `ChangeMe123!`（首次上线前必须更换）

电商评测集位于 `evaluation/datasets/ecommerce_qa_v1.jsonl`，共 180 条；数据集校验和压测报告位于 `evaluation/reports/`。真实模型、Embedding 和 Rerank 的生产参数模板见 `.env.production.example`。不要将真实密钥提交到仓库。
