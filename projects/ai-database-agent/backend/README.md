# FastAPI Backend

## 目录职责

```text
backend/
├── app/
│   ├── adapters/database/      # 数据库方言与驱动隔离
│   ├── adapters/llm/           # 大模型提供方适配
│   ├── agents/
│   │   ├── database_action/        # 意图路由、写操作规划和参数化SQL构造
│   │   ├── database_understanding/ # 提出证据需求并综合业务语义
│   │   ├── database_query/         # 自然语言查询规划与结果解释
│   │   ├── sql_generation/         # 按当前数据库方言生成取证SELECT
│   │   └── sql_execution/          # 校验语句类型并执行有界查询
│   ├── api/v1/endpoints/       # HTTP 接口
│   ├── core/                   # 配置、异常、日志
│   ├── graphs/
│   │   ├── understanding/      # 数据库理解与最多三轮自动取证
│   │   ├── query/              # 查询、执行、质检与重规划
│   │   ├── action/             # 跨表取值、单表写入与事务验证
│   │   └── conversation/       # Router、上下文合并与子流程调度
│   ├── models/                 # 与框架无关的领域模型
│   ├── repositories/           # 快照等数据的持久化抽象
│   ├── schemas/                # API 输入输出协议
│   ├── services/               # 业务用例编排
│   └── main.py                 # FastAPI 应用入口
├── data/snapshots/             # 本地数据库结构快照
├── data/connections/           # 无密码的连接Profile
├── data/credentials/           # 仅本机可读的加密连接凭据
├── data/understanding_runs/    # 表级理解结果
├── data/semantic_catalog/
│   ├── current/                # 每张表当前生效的语义版本
│   └── history/                # 不可变历史版本
├── data/semantic_reviews/
│   ├── current/                # 每个AI版本的最新审核修订
│   └── history/                # vN-rM不可变审核历史
├── data/database_queries/      # 自然语言查询运行、SQL与结果
├── data/checkpoints/           # LangGraph SQLite checkpoint
├── data/query_sessions/        # 多轮查询会话、意图与结果摘要
├── data/database_actions/      # 写操作计划、确认状态与执行审计
├── tests/
│   ├── unit/
│   └── integration/
├── .env                        # 本机配置，不提交版本库
└── pyproject.toml
```

依赖方向保持为：

```text
API -> Service -> LangGraph -> Agent / Adapter -> Database Driver
```

Agent 通过领域模型协作，endpoint 只负责触发业务用例，不包含Prompt、SQL生成或执行逻辑。

生产环境包含四层 LangGraph：

```text
Conversation Parent Graph
├── Query Graph
└── Action Graph

Understanding Graph（由数据库理解入口独立触发）
```

- Understanding Graph 编排分析、证据请求、SELECT生成与执行、带证据再分析，最多三轮；
- Query Graph 编排 `plan_query → execute_select → assess_result → replan/explain`；
- Action Graph 先跨表唯一解析业务名称，再生成单表写入预览；确认后事务执行并回查；
- Conversation Graph 统一完成 Router、确定性上下文合并以及 Query/Action 子流程调度。

Graph 负责流程和可恢复状态，原 Agent 继续负责 Prompt、结构化响应校验和语义硬约束。
业务结果仍写入各自 Repository，SQLite checkpointer 只保存节点状态，两者职责分离：

```text
data/checkpoints/understanding_graph.sqlite
data/checkpoints/query_graph.sqlite
data/checkpoints/action_graph.sqlite
data/checkpoints/conversation_graph.sqlite
```

数据库层支持 `mysql`、`postgresql`、`sqlserver`、`oracle`。Agent 不持有启动时创建的
固定连接，而是在每次运行时从 Snapshot 的 `connection_id` 解析 Adapter。标识符引用、
分页、参数绑定和写操作锁均由 `SqlDialect` 生成。

本地写权限由 FastAPI 强制校验，不依赖前端按钮。匿名请求是 `viewer`，只能查询；
登录后的 `database_operator` 才具备 Action Plan 和事务执行权限。

## 启动

确保本地 MySQL 容器已经启动：

```bash
cd projects/ai-database-agent/DB/mysql
docker compose up -d
```

启动 API：

```bash
cd projects/ai-database-agent/backend
uv sync
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

接口文档：

- Swagger UI：<http://127.0.0.1:8000/docs>
- OpenAPI JSON：<http://127.0.0.1:8000/openapi.json>

### 本地操作员登录

操作员凭据配置在 `.env`：

```text
AUTH_OPERATOR_USERNAME=db_operator
AUTH_OPERATOR_PASSWORD=请使用本机配置
AUTH_TOKEN_SECRET=请使用长随机值
AUTH_TOKEN_TTL_MINUTES=480
```

登录：

```bash
curl -c /tmp/semantica-cookie.txt \
  -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"db_operator","password":"本机配置的密码"}'
```

服务通过后端签名的 HttpOnly Cookie 保存会话。写操作接口还会再次进行角色校验，
直接绕过前端调用也无法匿名执行。

## 接口

### API 存活检查

```bash
curl http://127.0.0.1:8000/health/live
```

### 默认数据库连接检查

使用 `.env` 中的数据库配置：

```bash
curl http://127.0.0.1:8000/api/v1/database-connections/default/health
```

### 测试或保存指定数据库连接

```bash
curl -X POST http://127.0.0.1:8000/api/v1/database-connections/test \
  -H 'Content-Type: application/json' \
  -d '{
    "database_type": "mysql",
    "host": "127.0.0.1",
    "port": 3307,
    "database": "legacy_enterprise",
    "username": "ai_reader",
    "password": "local_reader_ChangeMe_2026",
    "connect_timeout_seconds": 5
  }'
```

密码使用 Pydantic `SecretStr` 接收，不会出现在响应中。当前接口面向本机开发；接入真实企业数据库前，需要增加身份认证、目标地址策略、限流和审计。

将 `/test` 改为 `/connect` 会在测试成功后返回 `connection_id`。Profile JSON 只保存
`credential_ref`，密码使用本机 `AUTH_TOKEN_SECRET` 派生的密钥加密后单独保存。
随后可直接扫描该连接：

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/database-snapshots/connections/{connection_id}/scan
```

其他数据库的 `database_type`、默认端口和默认 Schema：

| database_type | 默认端口 | 默认 Schema / 说明 |
| --- | ---: | --- |
| `mysql` | 3306 | Schema 即数据库名 |
| `postgresql` | 5432 | `public` |
| `sqlserver` | 1433 | `dbo`，运行机需安装 ODBC Driver 18 |
| `oracle` | 1521 | `database` 填 Service Name；Schema 默认使用大写用户名 |

### 扫描默认数据库结构

扫描表、字段、主键、索引、外键和注释，不读取业务表中的数据：

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/database-snapshots/default/scan
```

扫描结果保存在 `data/snapshots/{snapshot_id}.json`。响应中的
`snapshot_id` 可以用来重新读取快照：

```bash
curl \
  http://127.0.0.1:8000/api/v1/database-snapshots/{snapshot_id}
```

当前模拟数据库的预期扫描结果：

```text
table_count: 28
column_count: 256
foreign_key_count: 27
```

### 运行表级数据库理解 Agent

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/database-understanding/snapshots/{snapshot_id}/tables/{table_name}
```

理解流程会自动执行最多三轮SQL取证：

```text
Understanding Agent
  -> evidence_requests
  -> SQL Generation Agent
  -> SELECT type check
  -> SQL Execution Agent
  -> bounded query result
  -> Understanding Agent
```

SQL执行 Agent 当前使用首个语句关键字进行类型判断，只放行 `SELECT`。
每条查询最多向上游返回50行；查询SQL、执行状态和结果会保存在
`evidence_steps` 中。模型认为证据充分时提前结束，否则最多执行三轮。

最终响应不会把证据请求作为用户待办：

- `completion_status=completed`：Agent认为关键语义已经收敛。
- `completion_status=best_effort`：三轮后仍有歧义，以多个最佳候选收敛。
- `deferred_evidence_requests`：仅用于内部审计，不在前端显示为待处理项。
- `termination_reason`：记录提前收敛、达到轮数上限或SQL生成停滞等原因。

当前已经完成表级理解自动取证、Semantic Catalog、人工审核版本、结构化多轮查询，
以及写操作的计划、确认、事务执行和回查链路。查询 Agent 每轮执行后都会调用结果质检
Agent；SQL失败、空结果、异常粒度、字段歧义或证据查询可以触发重规划，最多三轮。

理解结果保存在：

```text
data/understanding_runs/{run_id}.json
```

理解成功后会自动发布 Semantic Catalog。相同运行重复发布不会增加版本；
同一张表由新的理解运行发布时，版本会从 v1 增加到 v2。

### Semantic Catalog

列出数据库已经沉淀的当前语义：

```bash
curl \
  http://127.0.0.1:8000/api/v1/semantic-catalog/databases/legacy_enterprise/tables
```

读取一张表的当前语义：

```bash
curl \
  http://127.0.0.1:8000/api/v1/semantic-catalog/databases/legacy_enterprise/tables/{table_name}
```

将已有理解运行发布到 Catalog：

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/semantic-catalog/runs/{run_id}/publish
```

Catalog 条目保存表级和字段级候选语义、数据粒度、声明关系、
Schema 指纹、完成状态、取证统计、来源快照及来源运行。

### 证据与人工审核

读取当前AI版本的完整证据：

```bash
curl \
  http://127.0.0.1:8000/api/v1/semantic-catalog/databases/legacy_enterprise/tables/{table_name}/evidence
```

提交字段审核：

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/semantic-catalog/databases/legacy_enterprise/tables/{table_name}/reviews \
  -H 'Content-Type: application/json' \
  -d '{
    "source_catalog_version": 1,
    "scope": "fields",
    "reviewer": "本地审核人",
    "field_decisions": [{
      "column_name": "gz",
      "reviewed_meaning": "实发工资",
      "reviewed_description": "员工本次实际到账金额",
      "source_candidate_index": 0,
      "note": ""
    }],
    "note": ""
  }'
```

审核不会覆盖AI版本。第一次审核生成 `v1-r1`，后续分批审核生成
`v1-r2` 并继承同一AI版本已确认的字段。整表审核要求提交表含义和全部字段。

### 运行自然语言查询 Agent

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/database-query/snapshots/{snapshot_id} \
  -H 'Content-Type: application/json' \
  -d '{"question":"按盘点状态统计盘点记录数量"}'
```

查询 Agent 优先使用与当前 AI Catalog 版本匹配的人工审核语义，没有审核时回退到
AI Catalog，再回退到 Schema。Agent 只生成 SELECT。每次执行后，结果质检 Agent 会判断
当前结果是否足以回答问题；若发现SQL失败、空结果与映射冲突、错误粒度、JOIN放大、
字段缺失、取证尚未形成答案或截断影响结论，会把真实结果和下一步建议交给规划 Agent，
最多循环三轮。每轮的 `plan_type`、SQL、结果和 `assessment` 都保存在
`data/database_queries/{query_id}.json`。

查询响应中的：

```json
{
  "workflow_engine": "langgraph",
  "workflow_thread_id": "query_..."
}
```

可用于确认本次查询由Graph执行。节点checkpoint保存在
`data/checkpoints/query_graph.sqlite`；它记录工作流恢复状态，不替代查询业务审计记录。

创建多轮查询会话：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/database-query/sessions \
  -H 'Content-Type: application/json' \
  -d '{"snapshot_id":"{snapshot_id}"}'
```

继续追问：

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/database-query/sessions/{session_id}/turns \
  -H 'Content-Type: application/json' \
  -d '{"message":"只看上海地区"}'
```

会话只把最近五轮成功查询的结构化意图和结果摘要交给模型。失败查询保留审计记录，
但不会覆盖当前有效上下文。

### 运行数据库写操作

统一对话入口会自动区分查询与持久化写操作。写操作要求携带操作员会话：

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/database-query/sessions/{session_id}/messages \
  -H 'Content-Type: application/json' \
  -d '{"message":"将客户编码 C00001 的客户状态设置为 ACTIVE"}'
```

写操作会继承最近查询的有界结果和业务主键，避免重新猜测年份或目标记录。
对于“吴凯改为研发工程师”“订单客户改为联华办公”等业务名称，规划 Agent 不允许猜测
数字外键，也不允许修改关联维度表的名称，而是声明 `value_lookups`。后端验证lookup必须
符合快照中的声明外键，然后用只读账号执行参数化SELECT；只有唯一匹配时才把ID写回
assignment或condition。没有匹配或多个候选会携带真实候选重规划，最多三轮，仍不唯一则
保存为 `blocked`，不会生成写入SQL。

解析完成后返回 `pending_confirmation` 计划，包含目标表、字段赋值、lookup证据、
AND条件、修改前数据、预计影响行数、安全检查和参数化SQL。确认执行：

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/database-actions/{action_id}/confirm
```

取消：

```bash
curl -X POST \
  http://127.0.0.1:8000/api/v1/database-actions/{action_id}/cancel
```

当前只允许单表 `INSERT`、`UPDATE`、`DELETE`。`UPDATE` 和 `DELETE` 必须包含条件，
默认最多影响 100 行，匹配0行时禁止确认；操作使用独立 `ai_writer` 账号，
在事务内重新锁定目标数据，
确认影响范围未漂移后执行并通过主键回查。验证失败会回滚。完整审计保存在：

```text
data/database_actions/{action_id}.json
```

`DROP`、`TRUNCATE`、`ALTER`、`CREATE`、多语句和多表写入暂不开放。

## 测试

```bash
uv run pytest
uv run ruff check .
```
