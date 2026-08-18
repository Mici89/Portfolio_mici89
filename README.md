# Enterprise AI Portfolio

面向招聘方和技术面试官的企业 AI 应用作品集。一个仓库包含三个独立项目和一个无需配置数据库、模型密钥即可浏览的展示站。

> 项目中的演示数据均为模拟或脱敏数据。仓库不包含 API Key、数据库密码、数据库运行文件、向量数据和本机运行时目录。

## 在线预览入口（本地）

启动后打开：

- 作品站：<http://localhost:3000>
- AI Database Agent：<http://localhost:3101/demo>
- 企信雷达：<http://localhost:3102>
- Enterprise Knowledge Agent：<http://localhost:3103>

## 一键启动

要求：Node.js 22+、Python 3.12+、uv、Docker Desktop，以及三个项目所需的本地环境变量。

建议在 macOS Terminal / iTerm 的独立窗口中运行启动器，不要在会自动回收后台进程的一次性命令执行器中运行。第一次启动会自动安装缺失的 Node/Python 依赖，之后会复用本地环境。

如果同级目录还保留着原来的三个项目，启动器会自动复用它们的 `.env`，这些文件只存在于本机且不会被 Git 跟踪。将仓库复制到另一台机器时，请根据各项目的 `.env.example` 自行配置密钥。

```bash
./scripts/start-all.sh
./scripts/status.sh
```

停止应用进程（默认不删除数据库卷）：

```bash
./scripts/stop-all.sh
```

统一启动端口：

| 服务 | 端口 |
| --- | ---: |
| 作品站 | 3000 |
| AI Database Agent Web / API | 3101 / 8101 |
| 企信雷达 | 3102 |
| Enterprise Knowledge Agent Web / API | 3103 / 8103 |
| MySQL | 3307 |
| Oracle | 1522 |
| PostgreSQL + pgvector | 5433 |

## 三个项目

### 01 · AI Database Agent

面向缺少注释、命名缩写严重、关系不完整的企业遗留数据库：扫描 Schema，结合真实数据进行有限轮次取证，生成可追溯语义目录；支持自然语言查询、上下文追问，以及经过影响预览和人工确认的数据库写操作。

技术栈：Python、FastAPI、React、TypeScript、LangGraph、DeepSeek、SQLAlchemy、MySQL / PostgreSQL / SQL Server / Oracle。

- 源码：[projects/ai-database-agent](projects/ai-database-agent/)
- 项目说明：[README](projects/ai-database-agent/README.md)
- 演示素材：[docs/portfolio](projects/ai-database-agent/docs/portfolio/README.md)

### 02 · 企信雷达

围绕企业主体检索，聚合工商与风险信息，通过确定性规则形成初步风险判断，再生成 AI 分析和 PDF / JSON 报告。

技术栈：Python、Streamlit、MCP、httpx、DeepSeek、ReportLab。

- 源码：[projects/enterprise-radar](projects/enterprise-radar/)
- 启动配置：[.env.example](projects/enterprise-radar/.env.example)

### 03 · Enterprise Knowledge Agent

支持 TXT、Markdown 和 PDF 文档上传、解析、切片与向量化；受控 Agent 在知识库边界内调用混合检索工具，并返回带原文引用和 Agent Trace 的回答。

技术栈：FastAPI、Next.js、PostgreSQL、pgvector、Ollama、DeepSeek。

- 源码：[projects/enterprise-knowledge-agent](projects/enterprise-knowledge-agent/)
- 项目说明：[README](projects/enterprise-knowledge-agent/README.md)
- 样例语料：[samples/enterprise_corpus](projects/enterprise-knowledge-agent/samples/enterprise_corpus/)

## 作品集的共同主线

```text
真实数据 / 文档取证
        ↓
受控 Agent 编排与工具调用
        ↓
可解释结果、人工确认与审计边界
```

三个项目分别覆盖结构化数据库、外部企业信息和内部非结构化知识，但都遵循同一工程原则：模型负责理解和规划，确定性代码负责边界、校验和执行。

## 目录结构

```text
enterprise-ai-portfolio/
├── README.md
├── site/                         # 作品展示站
├── projects/
│   ├── ai-database-agent/        # 数据库智能平台
│   ├── enterprise-radar/         # 企业风险分析
│   └── enterprise-knowledge-agent/ # 企业知识库智能体
└── scripts/                      # 统一启动、状态检查和停止
```

## 公开发布前检查

- 检查三个项目中的 `.env`、密钥和本地连接串没有被提交。
- 不提交 `DB/*/data`、`services/agent-api/storage`、虚拟环境和依赖目录。
- 不把真实企业数据、真实联系人信息或第三方接口返回结果放进演示素材。
- 将作品站中的本地体验链接替换为受限、只读、限流的线上演示后再公开。
