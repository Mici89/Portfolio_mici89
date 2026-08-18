# Enterprise AI Portfolio Hub

三个企业 AI 项目的统一作品入口。作品站与原项目保持独立，避免为了展示而耦合业务代码。

## 固定端口

| 服务 | 地址 / 端口 |
| --- | --- |
| 作品站 | http://localhost:3000 |
| AI Database Agent 前端 | http://localhost:3101 |
| AI Database Agent API | http://127.0.0.1:8101 |
| 企信雷达 | http://localhost:3102 |
| Enterprise Knowledge Agent 前端 | http://localhost:3103 |
| Enterprise Knowledge Agent API | http://127.0.0.1:8103 |
| AI Database Agent MySQL | 127.0.0.1:3307 |
| AI Database Agent Oracle | 127.0.0.1:1522 |
| Enterprise Knowledge Agent PostgreSQL | 127.0.0.1:5433 |

## 本地启动

```bash
./scripts/start-all.sh
./scripts/status.sh
```

停止应用进程（默认保留数据库容器）：

```bash
./scripts/stop-all.sh
```

日志和 PID 都保存在 `.runtime/`，不会写进三个业务项目。

启动器默认认为四个目录互为同级目录；如果实际路径不同，可以通过
`AI_DB_ROOT`、`QCC_ROOT` 和 `KNOWLEDGE_ROOT` 覆盖。

## 设计原则

- 招聘方打开作品站即可浏览，不要求数据库或 LLM Key。
- 三个真实项目使用独立端口、独立依赖和独立数据存储。
- 作品站只呈现可核验的功能、截图和演示数据，不混用不同数据库统计。
- 在线真实体验后续单独做只读、限流和脱敏，不把本地密钥打包到前端。
