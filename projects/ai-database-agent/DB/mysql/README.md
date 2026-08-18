# AI Database Agent MySQL 模拟企业数据库

这是一个面向数据库理解 Agent、关系发现、查询规划和 Text-to-SQL 评测的本地 MySQL 数据集。

## 当前状态

- MySQL：8.4
- 数据库：`legacy_enterprise`
- 端口：`3307`
- 表数量：28
- 数据量：58,518 行
- 业务范围：组织人事、CRM、产品、采购、销售、库存、报销、审批、薪资、考勤、收款、风控
- 注释质量：15 张规范表、6 张半规范表、7 张完全无注释遗留表
- 遗留命名：既包含 `c01`/`n01` 等抽象字段，也包含 `ygbh`/`rq`/`gz` 等中文拼音首字母字段
- 关系质量：规范模块有外键，遗留模块只有可从数据中推断的关系
- 数据异常：少量空值、孤立员工编码、历史 SKU、冲销记录和多种业务状态

## 目录

```text
mysql/
├── docker-compose.yml
├── data/                       # MySQL 数据文件，只保存在本机
├── init/
│   ├── 01_schema.sql           # 建表
│   ├── 02_seed.sql             # 确定性种子数据
│   └── 03_security.sql         # 将 ai_reader 收紧为只读用户
├── generator/
│   └── generate_seed.py        # 数据生成器
└── benchmark/
    ├── questions.md            # Agent 测试题
    ├── ground_truth.md         # 遗留字段真实语义，不应提供给 Agent
    └── validation.sql          # 数据集验证 SQL
```

## 连接信息

本地开发默认值：

```text
Host:     127.0.0.1
Port:     3307
Database: legacy_enterprise
User:     ai_reader
Password: local_reader_ChangeMe_2026
```

`ai_reader` 只有 `SELECT` 和 `SHOW VIEW` 权限，适合第一阶段的只读 Agent。

数据库写操作使用独立本地账号：

```text
User:     ai_writer
Password: local_writer_ChangeMe_2026
```

`ai_writer` 只有 `SELECT`、`INSERT`、`UPDATE`、`DELETE` 权限，不具备 DDL、
授权或数据库管理权限。后端仅在用户确认 Action Plan 后使用该连接。

默认 root 密码为 `local_root_ChangeMe_2026`，仅用于本机模拟环境。若数据库需要被其他机器访问，请先复制 `.env.example` 为 `.env` 并更换两个密码。

## 启动和停止

```bash
cd projects/ai-database-agent/DB/mysql
docker compose up -d
docker compose ps
docker compose stop
```

停止不会删除数据。再次 `docker compose up -d` 会继续使用 `data/` 中的数据。

## 连接数据库

容器内连接：

```bash
docker exec -it ai-db-legacy-mysql \
  mysql --default-character-set=utf8mb4 \
  -uai_reader -plocal_reader_ChangeMe_2026 legacy_enterprise
```

本机已安装 MySQL 客户端时：

```bash
mysql -h 127.0.0.1 -P 3307 \
  -uai_reader -plocal_reader_ChangeMe_2026 legacy_enterprise
```

## 重新生成种子 SQL

生成器只使用 Python 标准库，随机种子固定，重复执行会得到一致的数据：

```bash
python3 generator/generate_seed.py
```

初始化脚本只会在 `data/` 为空时由 MySQL 自动执行。若只是修改 `02_seed.sql`，正在运行的数据库不会自动重建。

如确实需要重建，先备份需要的数据，再停止容器并清空本目录的 `data/`。清空数据目录会永久删除当前数据库，因此不在 README 中提供自动删除命令。

## 验证

```bash
docker exec -i ai-db-legacy-mysql \
  mysql --default-character-set=utf8mb4 \
  -uai_reader -plocal_reader_ChangeMe_2026 legacy_enterprise \
  < benchmark/validation.sql
```

## Agent 使用建议

首次接入时只给 Agent：

- 数据库只读连接
- Schema/元数据扫描能力
- 受限的数据采样能力
- `benchmark/questions.md` 中的单个问题

不要把 `benchmark/ground_truth.md`、生成器源码或 SQL 初始化文件加入 Agent 的 RAG 知识库，否则会泄漏评测答案。
