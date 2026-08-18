"use client";

import { useMemo, useState } from "react";

import { createCatalogReview } from "@/lib/api";
import type {
  CatalogReviewCreate,
  CatalogReviewRevision,
  SemanticCatalogEntry,
  TableSchema,
} from "@/lib/types";

type FieldDraft = {
  candidateIndex: number | null;
  meaning: string;
  description: string;
};

export function CatalogReviewPanel({
  databaseName,
  connectionId,
  table,
  entry,
  latestReview,
  onCancel,
  onReviewed,
}: {
  databaseName: string;
  connectionId: string | null;
  table: TableSchema;
  entry: SemanticCatalogEntry;
  latestReview: CatalogReviewRevision | null;
  onCancel: () => void;
  onReviewed: (review: CatalogReviewRevision) => void;
}) {
  const effectiveAnalysis = latestReview?.reviewed_analysis ?? entry.analysis;
  const effectiveTableCandidate = effectiveAnalysis.table_candidates[0];
  const originalTableIndex = entry.analysis.table_candidates.findIndex(
    (candidate) => candidate.meaning === effectiveTableCandidate?.meaning,
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reviewer, setReviewer] = useState("");
  const [note, setNote] = useState("");
  const tableMeaning = effectiveTableCandidate?.meaning ?? "";
  const tableSummary = effectiveAnalysis.summary;
  const tableCandidateIndex = originalTableIndex >= 0 ? originalTableIndex : null;
  const [drafts, setDrafts] = useState<Record<string, FieldDraft>>(() => {
    const nextDrafts: Record<string, FieldDraft> = {};
    table.columns.forEach((column) => {
      const original = entry.analysis.columns.find(
        (item) => item.column_name === column.name,
      );
      const effective = effectiveAnalysis.columns.find(
        (item) => item.column_name === column.name,
      );
      const candidate = effective?.meaning_candidates[0];
      const originalIndex = original?.meaning_candidates.findIndex(
        (item) =>
          item.meaning === candidate?.meaning &&
          item.description === candidate?.description,
      );
      nextDrafts[column.name] = {
        candidateIndex:
          originalIndex !== undefined && originalIndex >= 0 ? originalIndex : null,
        meaning: candidate?.meaning ?? "",
        description: candidate?.description ?? "",
      };
    });
    return nextDrafts;
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const existingReviewedFields = useMemo(
    () => new Set(latestReview?.field_decisions.map((item) => item.column_name) ?? []),
    [latestReview],
  );

  const toggleField = (name: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const chooseCandidate = (columnName: string, value: string) => {
    if (value === "custom") {
      setDrafts((current) => ({
        ...current,
        [columnName]: {...current[columnName], candidateIndex: null},
      }));
      return;
    }
    const candidateIndex = Number(value);
    const semantic = entry.analysis.columns.find(
      (item) => item.column_name === columnName,
    );
    const candidate = semantic?.meaning_candidates[candidateIndex];
    if (!candidate) return;
    setDrafts((current) => ({
      ...current,
      [columnName]: {
        candidateIndex,
        meaning: candidate.meaning,
        description: candidate.description,
      },
    }));
  };

  const updateDraft = (
    columnName: string,
    key: "meaning" | "description",
    value: string,
  ) => {
    setDrafts((current) => ({
      ...current,
      [columnName]: {...current[columnName], [key]: value},
    }));
  };

  const submit = async (scope: "table" | "fields") => {
    if (!reviewer.trim()) {
      setError("请填写审核人");
      return;
    }
    if (scope === "fields" && selected.size === 0) {
      setError("请至少选择一个不同意的字段");
      return;
    }
    const submittedNames =
      scope === "table"
        ? table.columns.map((column) => column.name)
        : [...selected];
    const emptyField = submittedNames.find(
      (name) => !drafts[name]?.meaning.trim(),
    );
    if (emptyField) {
      setError(`${emptyField} 的审核含义不能为空`);
      return;
    }
    if (scope === "table" && (!tableMeaning.trim() || !tableSummary.trim())) {
      setError("整表审核需要填写表含义和表说明");
      return;
    }

    const payload: CatalogReviewCreate = {
      source_catalog_version: entry.version,
      scope,
      reviewer: reviewer.trim(),
      table_decision:
        scope === "table"
          ? {
              reviewed_meaning: tableMeaning.trim(),
              reviewed_summary: tableSummary.trim(),
              source_candidate_index: tableCandidateIndex,
              note: "",
            }
          : null,
      field_decisions: submittedNames.map((columnName) => ({
        column_name: columnName,
        reviewed_meaning: drafts[columnName].meaning.trim(),
        reviewed_description: drafts[columnName].description.trim(),
        source_candidate_index: drafts[columnName].candidateIndex,
        note: "",
      })),
      note: note.trim(),
    };

    setBusy(true);
    setError("");
    try {
      const review = await createCatalogReview(
        databaseName,
        table.name,
        payload,
        connectionId,
      );
      onReviewed(review);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "审核提交失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="review-workspace" aria-label="人工审核">
      <header className="review-heading">
        <div>
          <span className="eyebrow">Human Review</span>
          <h3>确认整表，或只修订有异议的字段</h3>
          <p>确认无误可一键通过；有异议时勾选字段直接修改，再生成审核版本。</p>
        </div>
        <button type="button" onClick={onCancel}>退出审核</button>
      </header>

      <div className="review-selection-summary">
        <div>
          <span>当前 Agent 表解释</span>
          <strong>{tableMeaning}</strong>
          <small>{tableSummary}</small>
        </div>
        <span>
          已标记 {selected.size}/{table.columns.length} 个异议字段
        </span>
      </div>

      <div className="review-meta-form">
        <label>
          <span>审核人</span>
          <input
            value={reviewer}
            onChange={(event) => setReviewer(event.target.value)}
            placeholder="输入姓名或工号"
          />
        </label>
        <label>
          <span>审核说明（可选）</span>
          <input
            value={note}
            onChange={(event) => setNote(event.target.value)}
            placeholder="例如：已与财务口径核对"
          />
        </label>
      </div>

      <div className="review-field-list">
        {table.columns.map((column) => {
          const semantic = entry.analysis.columns.find(
            (item) => item.column_name === column.name,
          );
          const draft = drafts[column.name];
          const isSelected = selected.has(column.name);
          const wasReviewed = existingReviewedFields.has(column.name);
          return (
            <article
              className={`review-field ${isSelected ? "review-field--selected" : ""}`}
              key={column.name}
            >
              <label className="review-field-check">
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleField(column.name)}
                />
                <span />
              </label>
              <div className="review-field-identity">
                <code>{column.name}</code>
                <small>{column.column_type}</small>
                {wasReviewed && <em>已审核</em>}
              </div>
              {isSelected ? (
                <div className="review-field-editor">
                  {semantic && semantic.meaning_candidates.length > 1 && (
                    <select
                      value={draft?.candidateIndex ?? "custom"}
                      onChange={(event) =>
                        chooseCandidate(column.name, event.target.value)
                      }
                      aria-label={`${column.name} 候选解释`}
                    >
                      {semantic.meaning_candidates.map((candidate, index) => (
                        <option value={index} key={`${candidate.meaning}-${index}`}>
                          候选 {index + 1}：{candidate.meaning}
                        </option>
                      ))}
                      <option value="custom">人工自定义</option>
                    </select>
                  )}
                  <input
                    aria-label={`${column.name} 审核含义`}
                    value={draft?.meaning ?? ""}
                    onChange={(event) =>
                      updateDraft(column.name, "meaning", event.target.value)
                    }
                    placeholder="输入确认后的字段含义"
                  />
                  <textarea
                    aria-label={`${column.name} 审核说明`}
                    value={draft?.description ?? ""}
                    onChange={(event) =>
                      updateDraft(column.name, "description", event.target.value)
                    }
                    placeholder="补充业务口径、编码含义或使用限制"
                    rows={2}
                  />
                </div>
              ) : (
                <div className="review-field-preview">
                  <strong>{draft?.meaning || "暂未确定"}</strong>
                  <small>{draft?.description || "没有补充说明"}</small>
                </div>
              )}
            </article>
          );
        })}
      </div>

      {error && <p className="form-error" role="alert">{error}</p>}
      <footer className="review-submit-bar">
        <span>
          将基于 AI v{entry.version} 生成{" "}
          {latestReview
            ? `v${entry.version}-r${latestReview.revision + 1}`
            : `v${entry.version}-r1`}
        </span>
        <div>
          <button
            className="review-submit-selected"
            type="button"
            disabled={busy || selected.size === 0}
            onClick={() => void submit("fields")}
          >
            提交 {selected.size} 个字段修订
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void submit("table")}
          >
            {busy ? "正在生成审核版本…" : "一键确认整表无误"}
          </button>
        </div>
      </footer>
    </section>
  );
}
