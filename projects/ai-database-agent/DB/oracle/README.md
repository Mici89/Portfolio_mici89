# 本地 Oracle 物流测试库

该目录提供一套只绑定 `127.0.0.1` 的 Oracle Free 23ai 物流模拟库。包含 16 张业务表、1200 张运单、约 2400 个包裹和 7000+ 条轨迹。设计刻意混合了清晰英文名、拼音缩写、历史字段（如 `C01`）和不完整注释，以测试数据库 Agent 的结构理解能力。

## 启动

```bash
cd projects/ai-database-agent/DB/oracle
cp .env.example .env
docker compose up -d
docker compose ps
```

首次启动需要下载镜像并初始化，通常需数分钟。初始化脚本只在空的 `data` 目录执行。

## 平台连接参数

| 参数 | 只读账号 | 可写账号 |
|---|---|---|
| 类型 | Oracle | Oracle |
| Host | `127.0.0.1` | `127.0.0.1` |
| Port | `1522` | `1522` |
| Service Name / Database | `FREEPDB1` | `FREEPDB1` |
| Username | `AI_READER` | `AI_WRITER` |
| Password | `Reader_2026_TestOnly` | `Writer_2026_TestOnly` |
| Schema | `LOGISTICS_APP` | `LOGISTICS_APP` |

对象所有者为 `LOGISTICS_APP`，密码见本地 `.env.example`。平台日常扫描建议先使用 `AI_READER`。

## 常用操作

```bash
docker compose logs -f oracle
docker compose stop
docker compose start
docker compose down
```

数据持久化在本机 `DB/oracle/data`。`docker compose down` 不删除它；如需全量重建，应先停止容器，再明确删除该目录中的数据库文件后重新启动。

## 设计说明

- 清晰表：`CUSTOMER`、`VEHICLE`、`PACKAGE_ITEM`、`DELIVERY_PROOF`。
- 历史风格表：`T_YD01`、`T_YD02`、`PS_GJ`、`T_X9`、`FY_JS`、`CK_JL`。
- 部分关系声明外键，部分仅通过运单号、客户编号、网点代码匹配，模拟遗留系统。
- 数据覆盖 2025-09 至 2026-08，并包含正常、延误、丢失、退回和在途状态。
- `AI_READER` 仅有查询权限；`AI_WRITER` 可执行常见 CRUD，适合写操作审批测试。
