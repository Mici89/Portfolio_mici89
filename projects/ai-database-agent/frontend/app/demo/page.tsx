"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

type Stage = "scan" | "understand" | "query" | "action";

const stages: Array<{ id: Stage; title: string; caption: string }> = [
  { id: "scan", title: "扫描结构", caption: "元数据与关系" },
  { id: "understand", title: "多轮取证", caption: "语义目录 v3" },
  { id: "query", title: "自然语言查询", caption: "SQL + 结果解释" },
  { id: "action", title: "人工确认写入", caption: "预览后执行" },
];

const queryRows = [
  ["华东", "上海", "2,184", "96.4%"],
  ["华东", "杭州", "1,276", "95.1%"],
  ["华南", "深圳", "1,089", "93.8%"],
];

export default function DemoPage() {
  const [stage, setStage] = useState<Stage>("scan");
  const [question, setQuestion] = useState("查询本月各区域已签收的运单数量和签收率");
  const [confirmed, setConfirmed] = useState(false);
  const stageIndex = stages.findIndex((item) => item.id === stage);
  const activeStage = stages[stageIndex];
  const sql = useMemo(
    () =>
      stage === "action"
        ? "UPDATE shipment_order\nSET delivery_note = :note\nWHERE tracking_no = :tracking_no"
        : "SELECT region_name, city_name, COUNT(DISTINCT shipment_id) AS signed_count,\n       ROUND(AVG(signed_rate) * 100, 1) AS signed_rate\nFROM shipment_fact\nWHERE signed_at >= :month_start\nGROUP BY region_name, city_name",
    [stage],
  );

  const next = () => {
    const nextStage = stages[Math.min(stageIndex + 1, stages.length - 1)].id;
    setStage(nextStage);
  };

  return (
    <main className="demo-page">
      <header className="demo-topbar">
        <Link href="/" className="demo-brand"><span>DB</span> DATA AGENT</Link>
        <div className="demo-topbar-right"><span className="demo-live-dot" /> 离线演示模式 <Link href="/">返回真实连接</Link></div>
      </header>

      <section className="demo-hero">
        <div>
          <span className="demo-kicker">PORTFOLIO DEMO · NO API KEY REQUIRED</span>
          <h1>让遗留数据库<br /><em>变得可理解、可追问、可控</em></h1>
          <p>一个面向物流业务的多 Agent 数据库工作台。以下流程使用内置模拟数据，不连接真实数据库，也不需要配置 LLM Key。</p>
        </div>
        <div className="demo-hero-card">
          <span className="demo-card-label">当前演示数据库</span>
          <strong>logistics_demo</strong>
          <div><span>16 张表</span><span>256 个字段</span><span>27 条关系</span></div>
          <small>SQLite fixture · deterministic mock LLM</small>
        </div>
      </section>

      <section className="demo-shell">
        <div className="demo-stepper" aria-label="演示流程">
          {stages.map((item, index) => (
            <button key={item.id} type="button" className={item.id === stage ? "active" : index < stageIndex ? "done" : ""} onClick={() => setStage(item.id)}>
              <span>{index < stageIndex ? "✓" : `0${index + 1}`}</span><strong>{item.title}</strong><small>{item.caption}</small>
            </button>
          ))}
        </div>

        <div className="demo-workspace">
          <aside className="demo-sidebar">
            <span className="demo-section-label">AGENT GRAPH</span>
            <div className="demo-agent-list">
              {[
                ["Understanding Agent", "已完成", "✓"],
                ["SQL Generation Agent", stageIndex >= 2 ? "已完成" : "等待", stageIndex >= 2 ? "✓" : "·"],
                ["SQL Execution Agent", stageIndex >= 2 ? "已完成" : "等待", stageIndex >= 2 ? "✓" : "·"],
                ["Action Planning Agent", stageIndex >= 3 ? "待确认" : "等待", stageIndex >= 3 ? "!" : "·"],
              ].map(([name, status, icon]) => <div className="demo-agent" key={name}><span className="demo-agent-icon">{icon}</span><div><strong>{name}</strong><small>{status}</small></div></div>)}
            </div>
            <div className="demo-sidebar-note"><span>安全策略</span><p>所有写操作必须经过影响预览和人工确认。</p></div>
          </aside>

          <div className="demo-main-panel">
            <div className="demo-panel-heading"><div><span className="demo-section-label">{activeStage.caption}</span><h2>{activeStage.title}</h2></div><span className="demo-status-pill">● LOCAL FIXTURE</span></div>

            {stage === "scan" && <div className="demo-scan-content">
              <div className="demo-metrics"><div><strong>16</strong><span>数据表</span></div><div><strong>256</strong><span>字段</span></div><div><strong>27</strong><span>外键关系</span></div><div><strong>3</strong><span>待理解表</span></div></div>
              <div className="demo-table-map"><div className="demo-map-title"><span>结构扫描结果</span><small>发现 3 个高价值业务域</small></div><div className="demo-map-grid"><div className="demo-map-card"><b>运单域</b><span>shipment_order</span><span>shipment_fact</span><span>shipment_trace</span></div><div className="demo-map-card"><b>客户域</b><span>customer_profile</span><span>address_book</span></div><div className="demo-map-card"><b>结算域</b><span>billing_record</span><span>payment_log</span></div></div></div>
            </div>}

            {stage === "understand" && <div className="demo-understand-content"><div className="demo-understand-head"><div><span className="demo-section-label">UNDERSTANDING GRAPH · ROUND 2/3</span><h3>shipment_order <span>语义版本 v3</span></h3></div><span className="demo-confidence">92% 置信度</span></div><p className="demo-summary">运单主表：一条记录代表一次客户寄件订单。通过字段分布、状态值和轨迹数据确认，<b>signed_at</b> 是业务签收时间，不能使用 created_at 替代。</p><div className="demo-evidence"><div><span>证据 SQL</span><code>SELECT status, COUNT(*) FROM shipment_order GROUP BY status</code></div><div><span>模型发现</span><strong>status = SIGNED 占比 68.4%</strong></div></div><div className="demo-tags"><span>结构证据</span><span>真实数据取证</span><span>人工可审核</span></div></div>}

            {stage === "query" && <div className="demo-query-content"><label className="demo-question-label">自然语言问题 <span>支持上下文追问</span></label><div className="demo-question-row"><input value={question} onChange={(event) => setQuestion(event.target.value)} /><button type="button" onClick={() => setStage("action")}>发送</button></div><div className="demo-query-grid"><div className="demo-sql-card"><div className="demo-card-head"><span>生成 SQL</span><span className="demo-validated">✓ 规则校验通过</span></div><pre>{sql}</pre><small>语义帧：shipment_fact · signed_at · COUNT(DISTINCT shipment_id)</small></div><div className="demo-result-card"><div className="demo-card-head"><span>查询结果</span><span>3 行</span></div><div className="demo-result-table"><div className="demo-result-row demo-result-header"><span>区域</span><span>城市</span><span>已签收</span><span>签收率</span></div>{queryRows.map((row) => <div className="demo-result-row" key={row.join("-")}>{row.map((cell) => <span key={cell}>{cell}</span>)}</div>)}</div></div></div></div>}

            {stage === "action" && <div className="demo-action-content"><div className="demo-action-warning"><span>!</span><div><strong>这是一个写操作</strong><p>系统不会直接执行，以下为影响预览。请确认后才会提交事务。</p></div></div><div className="demo-action-grid"><div><span className="demo-section-label">ACTION PLAN</span><h3>更新运单备注</h3><dl><dt>目标表</dt><dd>shipment_order</dd><dt>过滤条件</dt><dd>tracking_no = 'SF20260001'</dd><dt>预计影响</dt><dd>1 行</dd></dl></div><div className="demo-sql-card"><div className="demo-card-head"><span>预览 SQL</span><span className="demo-validated">✓ 有条件 · 有主键</span></div><pre>{sql}</pre><small>事务执行后将回查影响行数和主键值</small></div></div><button type="button" className={`demo-confirm-button ${confirmed ? "confirmed" : ""}`} onClick={() => setConfirmed(true)}>{confirmed ? "✓ 已确认，事务执行成功" : "确认并执行事务"}</button></div>}

            <div className="demo-footer-actions"><span>当前步骤：{stageIndex + 1} / {stages.length}</span>{stage !== "action" && <button type="button" onClick={next}>下一步 <span>→</span></button>}</div>
          </div>
        </div>
      </section>

      <footer className="demo-footer"><span>AI Database Agent · Portfolio Edition</span><span>离线演示数据仅用于作品展示</span></footer>
    </main>
  );
}
