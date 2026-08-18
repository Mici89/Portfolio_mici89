import Link from "next/link";
import { projects } from "../lib/projects";

export default function Home() {
  return (
    <main>
      <section className="hero">
        <div className="hero-copy">
          <p className="eyebrow">三个企业 AI 项目 · 一套完整作品集</p>
          <h1>从企业数据到知识，<br /><em>再到业务决策。</em></h1>
          <p className="hero-intro">这套作品集包含数据库智能平台、企业风险雷达和智能知识库。三个项目分别解决结构化数据理解、外部企业信息分析和内部文档问答，共同展示企业 AI 应用从数据接入、Agent 编排到安全交付的完整能力。</p>
          <div className="hero-actions"><Link className="button primary" href="#work">浏览三个项目</Link><Link className="button" href="#capabilities">查看能力图谱</Link></div>
        </div>
        <div className="portfolio-thesis" aria-label="作品集覆盖的三个业务方向">
          <div className="thesis-header"><span>portfolio scope</span><strong>03 enterprise AI systems</strong></div>
          <div className="thesis-path" aria-hidden="true"><i /><i /><i /></div>
          <div className="thesis-domains">
            <div className="cyan"><span>结构化数据</span><strong>理解数据库并安全操作</strong></div>
            <div className="amber"><span>外部企业信息</span><strong>识别风险并形成报告</strong></div>
            <div className="violet"><span>内部非结构化知识</span><strong>检索证据并可信作答</strong></div>
          </div>
          <p>共同方法：真实数据或文档取证 → 受控 Agent 行动 → 结果可解释与可追溯</p>
        </div>
      </section>

      <section className="work-section" id="work">
        <div className="section-heading"><p>Three projects</p><h2>选择一个项目，<br />查看具体功能和业务链路。</h2></div>
        <div className="project-list">
          {projects.map((project) => (
            <article className={`project-card ${project.accent}`} key={project.slug}>
              <div className="project-index">{project.index}</div>
              <div className="project-main">
                <p className="project-label">{project.label}</p><h3>{project.name}</h3><p>{project.summary}</p>
                <div className="stack-row">{project.stack.slice(0, 5).map((item) => <span key={item}>{item}</span>)}</div>
              </div>
              <div className="project-flow">{project.flow.map((step) => <span key={step}>{step}</span>)}</div>
              <Link className="case-link" href={`/projects/${project.slug}`}>查看完整案例 <span aria-hidden="true">↗</span></Link>
            </article>
          ))}
        </div>
      </section>

      <section className="capabilities" id="capabilities">
        <div className="section-heading"><p>What I build</p><h2>从模型调用，走到可用系统。</h2></div>
        <div className="capability-grid">
          <article><span>01 / Evidence</span><h3>检索与取证</h3><p>让 Schema、文档片段、外部工具结果成为模型判断的可追溯依据。</p></article>
          <article><span>02 / Orchestration</span><h3>Agent 编排</h3><p>用结构化状态、受控工具和有限轮次组织感知、行动与再规划。</p></article>
          <article><span>03 / Safety</span><h3>安全与确认</h3><p>把代码校验、影响预览、人工确认、事务回滚放在模型之外。</p></article>
          <article><span>04 / Delivery</span><h3>全栈交付</h3><p>从 FastAPI 服务到 React 界面、数据库适配、测试与本地部署。</p></article>
        </div>
      </section>

      <section className="about" id="about"><p className="eyebrow">About</p><h2>关注企业 AI 应用里最难落地的部分：上下文、证据、边界和交付。</h2><p>本作品站使用模拟或脱敏内容，无需招聘方准备数据库与模型密钥。项目案例会明确标注真实实现、演示方式和当前限制。</p></section>
    </main>
  );
}
