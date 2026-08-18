export type Project = {
  slug: string;
  index: string;
  name: string;
  shortName: string;
  label: string;
  summary: string;
  problem: string;
  outcome: string;
  accent: string;
  stack: string[];
  capabilities: string[];
  boundaries: string[];
  flow: string[];
  localUrl: string;
};

export const projects: Project[] = [
  {
    slug: "ai-database-agent",
    index: "A",
    name: "AI Database Agent",
    shortName: "Database Agent",
    label: "遗留数据库理解与安全操作",
    summary: "从缺少注释、缩写严重的企业数据库出发，用真实数据取证建立语义目录，再支持自然语言查询和人工确认后的写操作。",
    problem: "业务人员看不懂遗留表结构，也不会写 SQL；只看 Schema 的模型又容易误判字段含义。",
    outcome: "把数据库理解、证据、语义版本、查询结果和写操作审计放进同一条可追溯链路。",
    accent: "cyan",
    stack: ["FastAPI", "React", "TypeScript", "LangGraph", "DeepSeek", "SQLAlchemy"],
    capabilities: ["Schema 扫描与最多三轮数据取证", "AI 语义目录与人工审核版本", "上下文追问与真实查询结果", "Action Plan、影响预览、确认与事务执行"],
    boundaries: ["在线作品站不连接生产数据库", "访客演示只使用模拟或脱敏数据", "写操作必须经过操作员身份与明确确认"],
    flow: ["扫描结构", "证据取证", "发布语义", "自然语言查询", "人工确认写入"],
    localUrl: "http://localhost:3101/demo",
  },
  {
    slug: "enterprise-radar",
    index: "B",
    name: "企信雷达",
    shortName: "Enterprise Radar",
    label: "企业信息检索与风险分析",
    summary: "围绕企业主体检索，聚合工商与风险信息，通过可解释规则形成初步风险判断，并生成 AI 分析和可下载报告。",
    problem: "企业尽调信息分散，人工逐项查询慢，风险结论缺少统一口径和可交付报告。",
    outcome: "将企业选择、风险扫描、规则评分、AI 分析和 PDF 报告串成一次完整的尽调工作流。",
    accent: "amber",
    stack: ["Python", "Streamlit", "MCP", "DeepSeek", "httpx", "ReportLab"],
    capabilities: ["企业主体搜索与唯一标识选择", "工商和风险工具并发取数", "确定性风险规则与关注项", "AI 分析、JSON 与 PDF 报告导出"],
    boundaries: ["数据可用性取决于企查查 MCP 权限", "规则评分是辅助判断，不替代专业尽调", "公开演示不得展示真实 API Key"],
    flow: ["搜索企业", "选择主体", "并发取数", "风险评分", "生成报告"],
    localUrl: "http://localhost:3102",
  },
  {
    slug: "enterprise-knowledge-agent",
    index: "C",
    name: "Enterprise Knowledge Agent",
    shortName: "Knowledge Agent",
    label: "私有文档检索与可信问答",
    summary: "上传企业文档，完成解析、切片和向量化；受控 Agent 在知识库边界内调用混合检索工具，并返回带原文引用的回答。",
    problem: "企业文档分散，普通搜索难以组合证据，直接让模型回答又容易脱离资料。",
    outcome: "让每个回答都能回到文档片段，同时保留 Agent 的意图、步骤和实际工具调用轨迹。",
    accent: "violet",
    stack: ["FastAPI", "Next.js", "PostgreSQL", "pgvector", "Ollama", "DeepSeek"],
    capabilities: ["TXT、Markdown 与 PDF 上传解析", "切片、向量化与处理状态", "限定知识库的混合检索工具", "带引用回答与 Agent Trace"],
    boundaries: ["当前为单租户第一阶段", "暂不包含 SSO 与复杂权限", "资料不足时明确拒答，不补造引用"],
    flow: ["创建知识库", "上传文档", "解析与向量化", "Agent 检索", "引用回答"],
    localUrl: "http://localhost:3103",
  },
];

export function getProject(slug: string) {
  return projects.find((project) => project.slug === slug);
}
