"use client";

import type {
  CatalogEvidenceBundle,
  SemanticCandidate,
  SemanticCatalogEntry,
} from "@/lib/types";

const evidenceTypeLabels: Record<string, string> = {
  value_distribution: "取值分布",
  representative_rows: "代表性数据",
  relationship_match: "跨表关系验证",
  formula_check: "计算关系验证",
  numeric_statistics: "数值统计",
  date_range: "日期范围",
  string_pattern: "字符串格式",
};

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function SemanticEvidencePanel({
  entry,
  evidence,
  fieldName,
  onClose,
}: {
  entry: SemanticCatalogEntry;
  evidence: CatalogEvidenceBundle;
  fieldName: string | null;
  onClose: () => void;
}) {
  const column = fieldName
    ? entry.analysis.columns.find((item) => item.column_name === fieldName)
    : null;
  const candidate: SemanticCandidate | undefined = column
    ? column.meaning_candidates[0]
    : entry.analysis.table_candidates[0];
  const relationships = fieldName
    ? evidence.declared_relationships.filter(
        (relationship) =>
          relationship.source_columns.includes(fieldName) ||
          relationship.target_columns.includes(fieldName),
      )
    : evidence.declared_relationships;
  const targetedSteps = fieldName
    ? evidence.evidence_steps.filter((step) =>
        step.request.target_columns.some((target) =>
          target.split(".").includes(fieldName),
        ),
      )
    : evidence.evidence_steps;

  return (
    <section className="evidence-reader" aria-label="理解证据">
      <header className="evidence-reader-heading">
        <div>
          <span className="eyebrow">为什么这样理解</span>
          <h3>{fieldName ? `${fieldName} · 字段证据` : "整表理解证据"}</h3>
          <p>先看结论和业务依据，需要核查时再展开数据结果与原始 SQL。</p>
        </div>
        <button type="button" onClick={onClose}>关闭</button>
      </header>

      <div className="evidence-conclusion">
        <span>Agent 结论</span>
        <strong>{candidate?.meaning ?? "暂未形成明确结论"}</strong>
        <p>{candidate?.description || entry.analysis.summary}</p>
        {candidate && (
          <em>{Math.round(candidate.confidence * 100)}% 置信度</em>
        )}
      </div>

      <div className="evidence-reader-grid">
        <article className="evidence-readable-card">
          <span className="subheading">支持这个结论的线索</span>
          {candidate?.supporting_evidence.length ? (
            <ul>
              {candidate.supporting_evidence.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">本结论主要来自表结构、字段上下文和数据类型。</p>
          )}
          {candidate?.counter_evidence.length ? (
            <details className="counter-evidence">
              <summary>查看仍存在的反向证据</summary>
              <ul>
                {candidate.counter_evidence.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </article>

        <article className="evidence-readable-card">
          <span className="subheading">表间关系</span>
          {relationships.length ? (
            <div className="evidence-relations">
              {relationships.map((relationship) => (
                <div key={relationship.constraint_name}>
                  <code>
                    {relationship.source_table}.
                    {relationship.source_columns.join(",")}
                  </code>
                  <span>关联到</span>
                  <code>
                    {relationship.target_table}.
                    {relationship.target_columns.join(",")}
                  </code>
                  <small>数据库声明的外键关系</small>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted">
              {fieldName
                ? "数据库没有为该字段声明直接外键；仍可能通过下方数据取证发现隐式关系。"
                : "数据库没有为当前表声明外键关系。"}
            </p>
          )}
        </article>
      </div>

      <div className="evidence-query-section">
        <div className="evidence-query-heading">
          <span className="subheading">数据库取证过程</span>
          <small>{targetedSteps.length} 条与当前结论相关的查询</small>
        </div>
        {targetedSteps.length ? (
          targetedSteps.map((step, index) => {
            const columns = step.result.columns.slice(0, 6);
            const rows = step.result.rows.slice(0, 4);
            return (
              <details
                className={`readable-query readable-query--${step.result.status}`}
                key={`${step.round_number}-${index}-${step.query.sql}`}
              >
                <summary>
                  <span>第 {step.round_number} 轮</span>
                  <strong>
                    {evidenceTypeLabels[step.request.request_type] ??
                      step.query.purpose}
                  </strong>
                  <em>
                    {step.result.status === "executed"
                      ? `返回 ${step.result.returned_row_count} 行`
                      : step.result.status}
                  </em>
                </summary>
                <div className="readable-query-body">
                  <p>{step.request.reason}</p>
                  {step.result.status === "executed" ? (
                    <>
                      {rows.length > 0 && columns.length > 0 ? (
                        <div className="evidence-table-wrap">
                          <table>
                            <thead>
                              <tr>
                                {columns.map((name) => <th key={name}>{name}</th>)}
                              </tr>
                            </thead>
                            <tbody>
                              {rows.map((row, rowIndex) => (
                                <tr key={rowIndex}>
                                  {columns.map((name) => (
                                    <td key={name}>{displayValue(row[name])}</td>
                                  ))}
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <p className="muted">查询已执行，但没有返回示例行。</p>
                      )}
                      <small>
                        仅展示前 {rows.length} 行
                        {step.result.truncated ? "，完整结果已在执行阶段截断" : ""}
                      </small>
                    </>
                  ) : (
                    <p className="query-error">{step.result.error}</p>
                  )}
                  <details className="raw-sql">
                    <summary>查看原始 SQL</summary>
                    <pre><code>{step.query.sql}</code></pre>
                  </details>
                </div>
              </details>
            );
          })
        ) : (
          <div className="evidence-empty">
            当前字段没有单独的 SQL 取证记录，结论来自字段类型、命名、上下文及关联表结构。
          </div>
        )}
      </div>
    </section>
  );
}
