import { notFound } from "next/navigation";
import Link from "next/link";
import { ProjectDemo } from "../../../components/project-demo";
import { getProject, projects } from "../../../lib/projects";

export function generateStaticParams() { return projects.map(({ slug }) => ({ slug })); }

export default async function ProjectPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const project = getProject(slug);
  if (!project) notFound();

  return (
    <main className={`case-page ${project.accent}`}>
      <section className="case-hero">
        <Link className="back-link" href="/#work">← 返回全部项目</Link>
        <div className="case-hero-layout">
          <div className="case-hero-copy">
            <p className="eyebrow">Case {project.index} / {project.label}</p>
            <h1>{project.name}</h1><p>{project.summary}</p>
            <div className="stack-row">{project.stack.map((item) => <span key={item}>{item}</span>)}</div>
          </div>
          <aside className="case-entry" aria-label="本地完整体验入口">
            <div className="entry-status"><i /><span>本地服务已验证</span></div>
            <small>Full local experience</small>
            <h2>直接体验完整项目</h2>
            <p>包含真实前端流程与本地后端能力，无需从页面末尾寻找入口。</p>
            <a className="button primary" href={project.localUrl} target="_blank" rel="noreferrer">打开本地实例 ↗</a>
          </aside>
        </div>
      </section>
      <section className="case-split"><article><small>业务问题</small><h2>{project.problem}</h2></article><article><small>系统结果</small><h2>{project.outcome}</h2></article></section>
      <section className="case-section"><div className="section-heading"><p>Product walkthrough</p><h2>点击步骤，浏览核心功能链路。</h2></div><ProjectDemo slug={project.slug as "ai-database-agent" | "enterprise-radar" | "enterprise-knowledge-agent"} /></section>
      <section className="case-section columns"><div><p className="eyebrow">Implemented</p><h2>已实现能力</h2><ul className="check-list">{project.capabilities.map((item) => <li key={item}>{item}</li>)}</ul></div><div><p className="eyebrow">Boundaries</p><h2>当前边界</h2><ul className="boundary-list">{project.boundaries.map((item) => <li key={item}>{item}</li>)}</ul></div></section>
    </main>
  );
}
