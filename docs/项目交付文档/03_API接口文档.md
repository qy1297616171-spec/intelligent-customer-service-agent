# API 接口文档

基础地址：`/api/v1`；在线 OpenAPI：`/docs`。认证启用后使用 HttpOnly Cookie 或 `Authorization: Bearer <JWT>`，请求中的 `tenant_id` 必须与令牌一致。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/auth/login` | 登录并签发 Cookie |
| GET/POST/PATCH | `/auth/users[/{id}]` | 成员和角色管理 |
| GET | `/audit-logs` | 管理员读取审计 |
| GET/PATCH | `/customers[/{id}]` | 客户查询和更新 |
| GET | `/commerce/customers/{id}/orders` | 客户订单列表 |
| GET | `/commerce/orders/{order_no}` | 订单详情 |
| POST/GET | `/conversations` | 创建/查询会话 |
| GET | `/conversations/{id}/messages` | 消息历史 |
| POST | `/conversations/ask` | 智能问答 |
| POST/GET/PUT/DELETE | `/knowledge/documents[/{id}]` | 知识 CRUD |
| POST/GET/PATCH | `/handoffs[/{id}]` | 转人工与工单流转 |
| GET | `/analytics/overview` | 数据分析概览 |

问答请求示例：

```json
{"tenant_id":"demo-company","customer_id":"customer-2846","conversation_id":"uuid","question":"我的物流到哪了？"}
```

响应包含 `answer`、`answer_type`（`business_fact/knowledge/refusal`）、`grounded`、`latency_ms` 和 `citations`。常见状态码：400 参数错误、401 未登录、403 越权、404 资源不存在、409 数据冲突、422 校验失败、500 服务异常。

