# Enterprise Knowledge Agent

一个支持私有化部署的企业知识库智能体。

## 第一阶段目标

用户可以：

1. 上传 TXT、Markdown 和 PDF 文档
2. 创建并管理一个知识库
3. 对文档进行切片和向量化
4. 使用自然语言提问
5. 获得基于知识库生成的答案
6. 查看答案引用的原文片段

## 第一阶段暂不实现

- 多租户
- 用户登录和权限管理
- SSO
- 多智能体协作
- 复杂工作流
- 图片和音视频解析
- Kubernetes 部署

## 技术栈

- 后端：FastAPI
- 数据库：PostgreSQL + pgvector
- Agent/RAG：先实现基础流程，后续接入 LangGraph
- 前端：Next.js
- 部署：Docker Compose

## Agent 问答流程

问答接口使用受控的 Tool-Calling Agent，而不是固定的一次检索流程。Agent 在有限步数内根据问题调用以下工具：

- 混合知识库检索
- 已就绪文档列表
- 文档切片详情读取

每次工具调用都受到当前知识库边界限制。Agent 维护执行状态、检索证据和工具轨迹；只有引用编号与证据一致时才返回答案。资料不足或低于相似度阈值时，返回“根据现有知识库资料，无法回答该问题。”

`POST /knowledge-bases/{knowledge_base_id}/ask` 的响应包含 `agent_trace`，可用于观察识别出的意图、执行步数和实际调用的工具。
