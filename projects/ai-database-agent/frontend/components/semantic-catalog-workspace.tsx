"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { useDatabaseSession } from "@/components/database-session";
import { WorkspaceFrame } from "@/components/workspace-frame";
import {
  getCatalogEvidence,
  listLatestCatalogReviews,
  listSemanticCatalog,
} from "@/lib/api";
import type {
  CatalogEvidenceBundle,
  CatalogReviewRevision,
  SemanticCatalogEntry,
} from "@/lib/types";
import { CatalogReviewPanel } from "@/components/catalog-review-panel";
import { SemanticEvidencePanel } from "@/components/semantic-evidence-panel";

export function SemanticCatalogWorkspace() {
  const {ready, snapshot} = useDatabaseSession();
  const [entries, setEntries] = useState<SemanticCatalogEntry[]>([]);
  const [reviews, setReviews] = useState<CatalogReviewRevision[]>([]);
  const [selectedTable, setSelectedTable] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [evidence, setEvidence] = useState<CatalogEvidenceBundle | null>(null);
  const [evidenceField, setEvidenceField] = useState<string | null>(null);
  const [evidenceLoading, setEvidenceLoading] = useState(false);
  const [evidenceError, setEvidenceError] = useState("");

  useEffect(() => {
    if (!ready || !snapshot) {
      return;
    }
    let active = true;
    const load = async () => {
      setLoading(true);
      try {
        const [nextEntries, nextReviews] = await Promise.all([
          listSemanticCatalog(snapshot.database.name, snapshot.source.connection_id),
          listLatestCatalogReviews(
            snapshot.database.name,
            snapshot.source.connection_id,
          ),
        ]);
        if (!active) return;
        setEntries(nextEntries);
        setReviews(nextReviews);
        setSelectedTable(
          nextEntries[0]?.table_name ?? snapshot.tables[0]?.name ?? "",
        );
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "语义目录加载失败");
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [ready, snapshot]);

  const entryMap = useMemo(
    () => new Map(entries.map((entry) => [entry.table_name, entry])),
    [entries],
  );
  const tables = useMemo(
    () =>
      (snapshot?.tables ?? []).filter((table) =>
        `${table.name} ${table.comment}`
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [query, snapshot],
  );
  const table = snapshot?.tables.find((item) => item.name === selectedTable);
  const entry = entryMap.get(selectedTable);
  const latestReview = entry
    ? reviews
        .filter(
          (review) =>
            review.table_name === entry.table_name &&
            review.source_catalog_version === entry.version,
        )
        .sort((left, right) => right.revision - left.revision)[0] ?? null
    : null;
  const effectiveAnalysis = latestReview?.reviewed_analysis ?? entry?.analysis;
  const understoodColumns = effectiveAnalysis
    ? effectiveAnalysis.columns.filter(
        (column) => column.meaning_candidates.length > 0,
      ).length
    : 0;
  const coverage = snapshot?.tables.length
    ? Math.round((entries.length / snapshot.tables.length) * 100)
    : 0;

  const selectTable = (name: string) => {
    setSelectedTable(name);
    setReviewOpen(false);
    setEvidence(null);
    setEvidenceField(null);
    setEvidenceError("");
  };

  const openEvidence = async (fieldName: string | null) => {
    if (!snapshot || !entry) return;
    setReviewOpen(false);
    setEvidenceField(fieldName);
    setEvidenceError("");
    if (
      evidence?.table_name === entry.table_name &&
      evidence.catalog_version === entry.version
    ) {
      return;
    }
    setEvidenceLoading(true);
    try {
      const bundle = await getCatalogEvidence(
        snapshot.database.name,
        entry.table_name,
        snapshot.source.connection_id,
      );
      setEvidence(bundle);
    } catch (caught) {
      setEvidenceError(
        caught instanceof Error ? caught.message : "证据读取失败",
      );
    } finally {
      setEvidenceLoading(false);
    }
  };

  const acceptReview = (review: CatalogReviewRevision) => {
    setReviews((current) => [
      ...current.filter(
        (item) =>
          !(
            item.catalog_entry_id === review.catalog_entry_id &&
            item.source_catalog_version === review.source_catalog_version
          ),
      ),
      review,
    ]);
    setReviewOpen(false);
  };

  return (
    <WorkspaceFrame active="catalog">
      <section className="catalog-page">
        <header className="catalog-hero">
          <div>
            <span className="eyebrow">语义目录</span>
            <h1>数据库字段与业务含义</h1>
            <p>
              选择一张表，查看每个字段当前采用的解释、判断依据和人工审核结果。
            </p>
          </div>
          <div className="catalog-coverage">
            <strong>{coverage}%</strong>
            <span>{entries.length}/{snapshot?.tables.length ?? 0} 张表已理解</span>
            <Link href="/">去理解数据库</Link>
          </div>
        </header>

        {loading && <div className="catalog-loading">正在读取数据库与语义目录…</div>}
        {error && <p className="form-error" role="alert">{error}</p>}

        {!loading && snapshot && (
          <div className="catalog-layout">
            <aside className="catalog-sidebar">
              <div className="sidebar-heading">
                <span className="eyebrow">数据表</span>
                <strong>{snapshot.tables.length} 张</strong>
              </div>
              <label className="search-field">
                <span aria-hidden="true">⌕</span>
                <input
                  aria-label="搜索语义目录"
                  placeholder="搜索表名或注释"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                />
              </label>
              <div className="catalog-table-list">
                {tables.map((item) => {
                  const catalog = entryMap.get(item.name);
                  const review = catalog
                    ? reviews.find(
                        (candidate) =>
                          candidate.table_name === item.name &&
                          candidate.source_catalog_version === catalog.version,
                      )
                    : null;
                  return (
                    <button
                      key={item.name}
                      className={item.name === selectedTable ? "active" : ""}
                      onClick={() => selectTable(item.name)}
                      type="button"
                    >
                      <span className={catalog ? "covered" : "uncovered"} />
                      <span>
                        <strong>{item.name}</strong>
                        <small>
                          {catalog
                            ? `${review?.reviewed_analysis.table_candidates[0]?.meaning ?? catalog.analysis.table_candidates[0]?.meaning ?? "已理解"} · ${review?.display_version ?? `v${catalog.version}`}`
                            : "尚未生成语义"}
                        </small>
                      </span>
                      <em>{review?.display_version ?? (catalog ? `v${catalog.version}` : "—")}</em>
                    </button>
                  );
                })}
              </div>
            </aside>

            <section className="catalog-detail">
              {table && (
                <>
                  <div className="catalog-detail-heading">
                    <div>
                      <span className="eyebrow">物理表 → 业务语义</span>
                      <h2>{table.name}</h2>
                      <p>{table.comment || "数据库未提供表注释"}</p>
                    </div>
                    {entry ? (
                      <div className="catalog-detail-actions">
                        <div className="catalog-version-badge">
                          <strong>
                            {latestReview?.display_version ?? `v${entry.version}`}
                          </strong>
                          <span>
                            {latestReview
                              ? latestReview.status === "fully_reviewed"
                                ? "整表已审核"
                                : `${latestReview.reviewed_field_count}/${latestReview.total_field_count} 字段已审核`
                              : "尚未人工审核"}
                          </span>
                        </div>
                        <button
                          className="catalog-evidence-button"
                          type="button"
                          onClick={() => void openEvidence(null)}
                        >
                          查看理解证据
                        </button>
                        <button
                          className="catalog-review-button"
                          type="button"
                          onClick={() => {
                            setEvidence(null);
                            setReviewOpen(true);
                          }}
                        >
                          人工审核
                        </button>
                      </div>
                    ) : (
                      <span className="catalog-missing-badge">尚未理解</span>
                    )}
                  </div>

                  {entry ? (
                    <>
                      <div className="catalog-table-meaning">
                        <span>
                          {latestReview ? "当前审核解释" : "当前解释"}
                        </span>
                        <strong>
                          {effectiveAnalysis?.table_candidates[0]?.meaning ??
                            "保留候选解释"}
                        </strong>
                        <p>{effectiveAnalysis?.summary}</p>
                        <div>
                          <span>{entry.evidence_summary.database_query_rounds} 轮取证</span>
                          <span>{entry.evidence_summary.executed_query_count} 条SQL</span>
                          <span>{understoodColumns}/{table.columns.length} 字段有解释</span>
                          {latestReview && (
                            <span>审核人：{latestReview.reviewer}</span>
                          )}
                        </div>
                      </div>

                      {reviewOpen ? (
                        <CatalogReviewPanel
                          databaseName={snapshot.database.name}
                          connectionId={snapshot.source.connection_id}
                          table={table}
                          entry={entry}
                          latestReview={latestReview}
                          onCancel={() => setReviewOpen(false)}
                          onReviewed={acceptReview}
                        />
                      ) : (
                        <>
                          {evidenceLoading && (
                            <div className="catalog-loading">
                              正在整理可读证据…
                            </div>
                          )}
                          {evidenceError && (
                            <p className="form-error" role="alert">
                              {evidenceError}
                            </p>
                          )}
                          {evidence && !evidenceLoading && (
                            <SemanticEvidencePanel
                              entry={entry}
                              evidence={evidence}
                              fieldName={evidenceField}
                              onClose={() => {
                                setEvidence(null);
                                setEvidenceField(null);
                              }}
                            />
                          )}

                          <div className="catalog-field-map">
                            <div className="catalog-field-row catalog-field-row--header">
                              <span>物理字段</span>
                              <span>数据库注释</span>
                              <span>
                                {latestReview ? "当前审核解释" : "当前解释"}
                              </span>
                              <span>依据</span>
                            </div>
                            {table.columns.map((column) => {
                              const semantic = effectiveAnalysis?.columns.find(
                                (item) => item.column_name === column.name,
                              );
                              const candidate = semantic?.meaning_candidates[0];
                              const reviewed = latestReview?.field_decisions.find(
                                (item) => item.column_name === column.name,
                              );
                              return (
                                <div className="catalog-field-row" key={column.name}>
                                  <span>
                                    <code>{column.name}</code>
                                    <small>{column.column_type}</small>
                                  </span>
                                  <span className={column.comment ? "" : "muted"}>
                                    {column.comment || "无注释"}
                                  </span>
                                  <span>
                                    <strong>{candidate?.meaning ?? "暂未确定"}</strong>
                                    <small>
                                      {candidate?.description ||
                                        semantic?.status ||
                                        "unknown"}
                                    </small>
                                    {reviewed && (
                                      <em className="field-reviewed-badge">
                                        {reviewed.decision === "edited"
                                          ? "人工修订"
                                          : "人工确认"}
                                      </em>
                                    )}
                                  </span>
                                  <span className="catalog-field-actions">
                                    <em>
                                      {candidate
                                        ? `${Math.round(candidate.confidence * 100)}%`
                                        : "—"}
                                    </em>
                                    <button
                                      type="button"
                                      onClick={() => void openEvidence(column.name)}
                                    >
                                      查看依据
                                    </button>
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </>
                      )}
                    </>
                  ) : (
                    <div className="catalog-empty-table">
                      <strong>这张表还没有字段解释</strong>
                      <p>回到理解数据库页面，重新理解当前表或整个数据库。</p>
                      <Link href="/">去理解数据库</Link>
                    </div>
                  )}
                </>
              )}
            </section>
          </div>
        )}
      </section>
    </WorkspaceFrame>
  );
}
