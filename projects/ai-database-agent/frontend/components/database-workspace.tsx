"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";

import { useDatabaseSession } from "@/components/database-session";
import { WorkspaceFrame } from "@/components/workspace-frame";
import {
  ApiRequestError,
  connectDatabase,
  friendlyApiError,
  getCatalogBuild,
  listSemanticCatalog,
  resumeUnderstandingRun,
  scanDefaultDatabase,
  scanSavedConnection,
  startCatalogBuild,
  testDefaultConnection,
  understandTable,
} from "@/lib/api";
import type {
  CatalogBuildJob,
  ConnectionConfig,
  ConnectionInfo,
  DatabaseSnapshot,
  SemanticCandidate,
  SemanticCatalogEntry,
  TableSchema,
  UnderstandingRun,
} from "@/lib/types";

const initialConnection: ConnectionConfig = {
  database_type: "mysql",
  host: "127.0.0.1",
  port: 3307,
  database: "legacy_enterprise",
  username: "ai_reader",
  password: "",
  schema_name: null,
  connect_timeout_seconds: 5,
};

function formatCount(value: number | null): string {
  if (value === null) return "—";
  return new Intl.NumberFormat("zh-CN").format(value);
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function confidenceLabel(confidence: number): string {
  if (confidence >= 0.85) return "高";
  if (confidence >= 0.65) return "中";
  return "低";
}

function CandidateCard({
  candidate,
  compact = false,
}: {
  candidate: SemanticCandidate;
  compact?: boolean;
}) {
  const percent = Math.round(candidate.confidence * 100);
  return (
    <article className={`candidate-card ${compact ? "candidate-card--compact" : ""}`}>
      <div className="candidate-title-row">
        <div>
          <span className="eyebrow">{confidenceLabel(candidate.confidence)}置信度</span>
          <h4>{candidate.meaning}</h4>
        </div>
        <strong>{percent}%</strong>
      </div>
      <div className="confidence-track" aria-label={`置信度 ${percent}%`}>
        <span style={{ width: `${percent}%` }} />
      </div>
      {candidate.description && <p>{candidate.description}</p>}
      {!compact && candidate.supporting_evidence.length > 0 && (
        <ul className="evidence-list">
          {candidate.supporting_evidence.slice(0, 3).map((evidence) => (
            <li key={evidence}>{evidence}</li>
          ))}
        </ul>
      )}
    </article>
  );
}

function ConnectionPanel({
  connection,
  setConnection,
  onSubmit,
  onDefault,
  busy,
  message,
  error,
}: {
  connection: ConnectionConfig;
  setConnection: (value: ConnectionConfig) => void;
  onSubmit: (event: FormEvent) => void;
  onDefault: () => void;
  busy: boolean;
  message: string;
  error: string;
}) {
  const update = <Key extends keyof ConnectionConfig>(
    key: Key,
    value: ConnectionConfig[Key],
  ) => setConnection({ ...connection, [key]: value });
  const databaseLabels = {
    mysql: "MySQL",
    postgresql: "PostgreSQL",
    sqlserver: "SQL Server",
    oracle: "Oracle",
  };
  const selectDatabaseType = (databaseType: ConnectionConfig["database_type"]) => {
    const defaults = {
      mysql: {port: 3306, schema_name: null},
      postgresql: {port: 5432, schema_name: "public"},
      sqlserver: {port: 1433, schema_name: "dbo"},
      oracle: {port: 1521, schema_name: null},
    };
    setConnection({
      ...connection,
      database_type: databaseType,
      ...defaults[databaseType],
    });
  };

  return (
    <section className="connect-shell">
      <div className="connect-copy">
        <span className="product-kicker">数据工作台</span>
        <h1>连接数据库</h1>
        <p>
          填写数据库连接信息。连接成功后，可以理解数据库结构、查看字段解释，
          也可以直接用自然语言查询和修改数据。
        </p>
        <div className="entry-capabilities">
          <div><strong>理解数据库</strong><span>读取表、字段和关联关系</span></div>
          <div><strong>语义目录</strong><span>查看解释、证据和审核结果</span></div>
          <div><strong>智能对话</strong><span>查询数据，确认后执行修改</span></div>
        </div>
      </div>

      <form className="connection-card" onSubmit={onSubmit}>
        <div className="card-heading">
          <div>
            <span className="status-dot" />
            <span>数据库连接</span>
          </div>
          <span className="mysql-badge">{databaseLabels[connection.database_type]}</span>
        </div>

        <div className="form-grid">
          <label className="field field--wide">
            <span>数据库类型</span>
            <select
              value={connection.database_type}
              onChange={(event) =>
                selectDatabaseType(event.target.value as ConnectionConfig["database_type"])
              }
            >
              <option value="mysql">MySQL</option>
              <option value="postgresql">PostgreSQL</option>
              <option value="sqlserver">Microsoft SQL Server</option>
              <option value="oracle">Oracle Database</option>
            </select>
          </label>
          <label className="field field--wide">
            <span>主机地址</span>
            <input
              value={connection.host}
              onChange={(event) => update("host", event.target.value)}
              autoComplete="off"
            />
          </label>
          <label className="field">
            <span>端口</span>
            <input
              type="number"
              value={connection.port}
              onChange={(event) => update("port", Number(event.target.value))}
            />
          </label>
          <label className="field">
            <span>连接超时</span>
            <div className="input-suffix">
              <input
                type="number"
                value={connection.connect_timeout_seconds}
                onChange={(event) =>
                  update("connect_timeout_seconds", Number(event.target.value))
                }
              />
              <span>秒</span>
            </div>
          </label>
          <label className="field field--wide">
            <span>{connection.database_type === "oracle" ? "Service Name" : "数据库"}</span>
            <input
              value={connection.database}
              onChange={(event) => update("database", event.target.value)}
              autoComplete="off"
            />
          </label>
          {(connection.database_type === "postgresql" ||
            connection.database_type === "sqlserver" ||
            connection.database_type === "oracle") && (
            <label className="field field--wide">
              <span>Schema（可选）</span>
              <input
                value={connection.schema_name ?? ""}
                onChange={(event) => update("schema_name", event.target.value || null)}
                placeholder={
                  connection.database_type === "postgresql"
                    ? "public"
                    : connection.database_type === "sqlserver"
                      ? "dbo"
                      : "默认使用用户名"
                }
              />
            </label>
          )}
          <label className="field">
            <span>用户名</span>
            <input
              value={connection.username}
              onChange={(event) => update("username", event.target.value)}
              autoComplete="username"
            />
          </label>
          <label className="field">
            <span>密码</span>
            <input
              type="password"
              value={connection.password}
              onChange={(event) => update("password", event.target.value)}
              placeholder="输入数据库密码"
              autoComplete="current-password"
              required
            />
          </label>
        </div>

        {message && <p className="form-message">{message}</p>}
        {error && <p className="form-error" role="alert">{error}</p>}

        <button className="primary-button" type="submit" disabled={busy}>
          {busy ? <span className="button-loader" /> : <span>连接并扫描结构</span>}
          <span aria-hidden="true">→</span>
        </button>
        <button
          className="text-button"
          type="button"
          onClick={onDefault}
          disabled={busy}
        >
          使用本机默认配置
        </button>
        <Link className="demo-entry-link" href="/demo">
          查看无需配置的离线作品演示 →
        </Link>
      </form>
    </section>
  );
}

function TableList({
  tables,
  catalogEntries,
  selected,
  onSelect,
}: {
  tables: TableSchema[];
  catalogEntries: SemanticCatalogEntry[];
  selected: string;
  onSelect: (name: string) => void;
}) {
  const [query, setQuery] = useState("");
  const filtered = useMemo(
    () =>
      tables.filter((table) =>
        `${table.name} ${table.comment}`.toLowerCase().includes(query.toLowerCase()),
      ),
    [query, tables],
  );

  return (
    <aside className="table-sidebar">
      <div className="sidebar-heading">
        <span className="eyebrow">数据表</span>
        <strong>{tables.length} 张</strong>
      </div>
      <label className="search-field">
        <span aria-hidden="true">⌕</span>
        <input
          aria-label="搜索数据表"
          placeholder="搜索表名或注释"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </label>
      <div className="table-list">
        {filtered.map((table) => (
          <button
            key={table.name}
            className={`table-item ${selected === table.name ? "table-item--active" : ""}`}
            onClick={() => onSelect(table.name)}
            type="button"
          >
            <span className="table-item-select">
              <span className="table-icon">
                {catalogEntries.some((entry) => entry.table_name === table.name) ? "✓" : "?"}
              </span>
              <span>
                <strong>{table.name}</strong>
                <small>
                  {catalogEntries.find((entry) => entry.table_name === table.name)
                    ? `语义版本 v${catalogEntries.find((entry) => entry.table_name === table.name)?.version}`
                    : "无语义版本 · 待理解"}
                </small>
              </span>
              <em>{table.columns.length}</em>
            </span>
          </button>
        ))}
      </div>
    </aside>
  );
}

function StructurePanel({
  table,
  snapshot,
  onUnderstand,
  busy,
  error,
  canResume,
  onResume,
}: {
  table: TableSchema;
  snapshot: DatabaseSnapshot;
  onUnderstand: () => void;
  busy: boolean;
  error: string;
  canResume: boolean;
  onResume: () => void;
}) {
  const relationships = snapshot.declared_relationships.filter(
    (relationship) =>
      relationship.source_table === table.name ||
      relationship.target_table === table.name,
  );
  return (
    <section className="structure-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">表结构</span>
          <h2>{table.name}</h2>
          <p>{table.comment || "数据库没有提供注释，系统会结合字段、数据和表间关系进行判断。"}</p>
        </div>
        <button className="agent-button" onClick={onUnderstand} disabled={busy}>
          {busy ? (
            <>
              <span className="button-loader button-loader--dark" />
              正在理解
            </>
          ) : (
            "重新理解当前表"
          )}
          {!busy && <span aria-hidden="true">✦</span>}
        </button>
      </div>
      {error && (
        <div className="workflow-recovery" role="alert">
          <p className="form-error">{error}</p>
          {canResume && (
            <button type="button" onClick={onResume} disabled={busy}>
              {busy ? "正在恢复…" : "从上次断点继续"}
            </button>
          )}
        </div>
      )}
      <p className="single-table-hint">
        表结构发生变化时，可以只更新当前表的解释。
      </p>

      <div className="relationship-strip">
        <div>
          <span className="eyebrow">表粒度线索</span>
          <strong>{table.primary_key.length ? table.primary_key.join(" + ") : "无声明主键"}</strong>
        </div>
        <div>
          <span className="eyebrow">预计行数</span>
          <strong>{formatCount(table.estimated_row_count)}</strong>
        </div>
        <div>
          <span className="eyebrow">直接关系</span>
          <strong>{relationships.length}</strong>
        </div>
      </div>

      {relationships.length > 0 && (
        <div className="relationship-list">
          {relationships.map((relationship) => (
            <div key={relationship.constraint_name}>
              <code>{relationship.source_table}.{relationship.source_columns.join(",")}</code>
              <span>→</span>
              <code>{relationship.target_table}.{relationship.target_columns.join(",")}</code>
            </div>
          ))}
        </div>
      )}

      <div className="column-table">
        <div className="column-row column-row--header">
          <span>字段</span><span>类型</span><span>约束</span><span>注释</span>
        </div>
        {table.columns.map((column) => (
          <div className="column-row" key={column.name}>
            <code>{column.name}</code>
            <span>{column.column_type}</span>
            <span className="constraint-cell">
              {column.is_primary_key && <em>PK</em>}
              {column.is_unique && <em>UQ</em>}
              {!column.nullable && <em>NN</em>}
            </span>
            <span className={column.comment ? "" : "muted"}>
              {column.comment || "—"}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

function UnderstandingPanel({
  run,
  table,
}: {
  run: UnderstandingRun | null;
  table: TableSchema;
}) {
  if (!run) {
    return (
      <aside className="understanding-panel understanding-panel--empty">
        <span className="empty-orbit">✦</span>
        <span className="eyebrow">字段解释</span>
        <h3>等待理解</h3>
        <p>选择一张表并开始理解，结果会显示在这里。</p>
      </aside>
    );
  }
  const columnMap = new Map(
    run.analysis.columns.map((column) => [column.column_name, column]),
  );
  return (
    <aside className="understanding-panel">
      <div className="analysis-heading">
        <div>
          <span className="eyebrow">字段解释</span>
          <h3>
            {run.completion_status === "best_effort"
              ? "三轮后的最佳结论"
              : run.analysis.status === "ambiguous"
                ? "保留多个候选"
                : run.evidence_steps.length > 0
                  ? "数据取证推断"
                  : "结构级推断"}
          </h3>
        </div>
        <span className={`analysis-status analysis-status--${run.analysis.status}`}>
          {run.analysis.status}
        </span>
      </div>
      <p className="analysis-summary">{run.analysis.summary}</p>

      <div className="candidate-stack">
        <span className="subheading">表含义候选</span>
        {run.analysis.table_candidates.map((candidate) => (
          <CandidateCard key={candidate.meaning} candidate={candidate} />
        ))}
      </div>

      <div className="semantic-columns">
        <span className="subheading">字段候选</span>
        {table.columns.map((column) => {
          const analysis = columnMap.get(column.name);
          const candidates = analysis?.meaning_candidates ?? [];
          return (
            <details key={column.name} className="semantic-column">
              <summary>
                <code>{column.name}</code>
                <span>{candidates[0]?.meaning ?? "暂时未知"}</span>
                <em>{candidates[0] ? `${Math.round(candidates[0].confidence * 100)}%` : "—"}</em>
              </summary>
              <div className="semantic-column-body">
                {candidates.length > 0 ? (
                  candidates.map((candidate) => (
                    <CandidateCard key={candidate.meaning} candidate={candidate} compact />
                  ))
                ) : (
                  <p className="muted">结构证据不足，等待数据画像。</p>
                )}
              </div>
            </details>
          );
        })}
      </div>

      {run.evidence_steps.length > 0 && (
        <div className="evidence-trace">
          <span className="subheading">自动取证轨迹</span>
          {run.evidence_steps.map((step, index) => (
            <details
              className={`evidence-step evidence-step--${step.result.status}`}
              key={`${step.round_number}-${index}-${step.query.sql}`}
            >
              <summary>
                <span>R{step.round_number}</span>
                <strong>{step.query.purpose}</strong>
                <em>{step.result.status}</em>
              </summary>
              <div className="evidence-step-body">
                <p>{step.request.reason}</p>
                <pre><code>{step.query.sql}</code></pre>
                {step.result.status === "executed" ? (
                  <>
                    <small>
                      返回 {step.result.returned_row_count} 行
                      {step.result.truncated ? " · 结果已截断" : ""}
                    </small>
                    {step.result.rows.length > 0 && (
                      <pre className="query-result">
                        {JSON.stringify(step.result.rows.slice(0, 3), null, 2)}
                      </pre>
                    )}
                  </>
                ) : (
                  <p className="query-error">{step.result.error}</p>
                )}
              </div>
            </details>
          ))}
        </div>
      )}

      <footer className="analysis-footer">
        <span>{run.model}</span>
        <span>{formatCount(run.usage.total_tokens)} tokens</span>
        <span>
          {run.evidence_round_count}/{run.max_evidence_rounds} 轮
          {run.completion_status === "completed" ? " · 已收敛" : " · 最佳结论"}
        </span>
        <span>
          {run.evidence_scope === "schema_only"
            ? "仅结构证据"
            : run.evidence_scope === "schema_and_query_evidence"
              ? "结构 + SQL 实证"
              : "结构 + 画像"}
        </span>
        {run.catalog_version !== null && (
          <span>Semantic Catalog v{run.catalog_version}</span>
        )}
      </footer>
    </aside>
  );
}

export function DatabaseWorkspace() {
  const {
    ready,
    connectionInfo,
    snapshot,
    connect,
  } = useDatabaseSession();
  const [connection, setConnection] = useState(initialConnection);
  const [selectedTableName, setSelectedTableName] = useState("");
  const [understandingRun, setUnderstandingRun] = useState<UnderstandingRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [agentBusy, setAgentBusy] = useState(false);
  const [catalogBuildBusy, setCatalogBuildBusy] = useState(false);
  const [catalogBuild, setCatalogBuild] = useState<CatalogBuildJob | null>(null);
  const [catalogBuildError, setCatalogBuildError] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [agentError, setAgentError] = useState("");
  const [recoverableRunId, setRecoverableRunId] = useState("");
  const [catalogEntries, setCatalogEntries] = useState<SemanticCatalogEntry[]>([]);

  const selectedTable =
    snapshot?.tables.find((table) => table.name === selectedTableName) ??
    snapshot?.tables[0] ??
    null;

  const finishScan = async (info: ConnectionInfo, nextSnapshot: DatabaseSnapshot) => {
    const entries = await listSemanticCatalog(
      nextSnapshot.database.name,
      nextSnapshot.source.connection_id ?? info.connection_id,
    ).catch(() => []);
    setCatalogEntries(entries);
    connect(
      {...info, connection_id: nextSnapshot.source.connection_id},
      nextSnapshot,
    );
    setSelectedTableName(
      nextSnapshot.tables.find(
        (table) => !entries.some((entry) => entry.table_name === table.name),
      )?.name ?? nextSnapshot.tables[0]?.name ?? "",
    );
    setUnderstandingRun(null);
  };

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setMessage("正在验证连接…");
    try {
      const info = await connectDatabase(connection);
      if (!info.connection_id) {
        throw new Error("后端没有返回连接标识");
      }
      setMessage("连接成功，正在读取数据库结构…");
      const nextSnapshot = await scanSavedConnection(info.connection_id);
      await finishScan(info, nextSnapshot);
    } catch (caught) {
      setError(friendlyApiError(caught, "连接失败"));
    } finally {
      setBusy(false);
      setMessage("");
    }
  };

  const handleDefault = async () => {
    setBusy(true);
    setError("");
    setMessage("正在使用后端默认连接扫描…");
    try {
      const [info, nextSnapshot] = await Promise.all([
        testDefaultConnection(),
        scanDefaultDatabase(),
      ]);
      await finishScan(info, nextSnapshot);
    } catch (caught) {
      setError(friendlyApiError(caught, "默认连接不可用"));
    } finally {
      setBusy(false);
      setMessage("");
    }
  };

  const handleUnderstand = async (tableName = selectedTable?.name) => {
    if (!snapshot || !tableName) return;
    setSelectedTableName(tableName);
    setUnderstandingRun(null);
    setAgentBusy(true);
    setAgentError("");
    setRecoverableRunId("");
    try {
      const run = await understandTable(snapshot.snapshot_id, tableName);
      setUnderstandingRun(run);
      setCatalogEntries(
        await listSemanticCatalog(
          snapshot.database.name,
          snapshot.source.connection_id ?? connectionInfo?.connection_id ?? null,
        ).catch(() => catalogEntries),
      );
    } catch (caught) {
      setAgentError(friendlyApiError(caught, "当前表理解失败"));
      if (
        caught instanceof ApiRequestError &&
        caught.workflowKind === "understanding" &&
        caught.workflowId
      ) {
        setRecoverableRunId(caught.workflowId);
      }
    } finally {
      setAgentBusy(false);
    }
  };

  const handleResumeUnderstanding = async () => {
    if (!recoverableRunId) return;
    setAgentBusy(true);
    setAgentError("");
    try {
      const run = await resumeUnderstandingRun(recoverableRunId);
      setUnderstandingRun(run);
      setRecoverableRunId("");
    } catch (caught) {
      setAgentError(friendlyApiError(caught, "断点恢复失败"));
    } finally {
      setAgentBusy(false);
    }
  };

  const handleBuildCatalog = async () => {
    if (!snapshot) return;
    setCatalogBuildBusy(true);
    setCatalogBuildError("");
    try {
      let job = await startCatalogBuild(snapshot.snapshot_id);
      setCatalogBuild(job);
      while (job.status === "queued" || job.status === "running") {
        await wait(1500);
        job = await getCatalogBuild(job.job_id);
        setCatalogBuild(job);
      }
    } catch (caught) {
      setCatalogBuildError(friendlyApiError(caught, "全库理解任务启动失败"));
    } finally {
      setCatalogBuildBusy(false);
    }
  };

  const selectTable = (name: string) => {
    setSelectedTableName(name);
    setUnderstandingRun(null);
    setAgentError("");
    setRecoverableRunId("");
  };

  const progress = catalogBuild?.total_tables
    ? Math.round((catalogBuild.processed_tables / catalogBuild.total_tables) * 100)
    : 0;

  if (!ready) {
    return <main className="session-loading">正在读取数据库会话…</main>;
  }

  if (!snapshot || !connectionInfo) {
    return (
      <main className="connection-page">
        <ConnectionPanel
          connection={connection}
          setConnection={setConnection}
          onSubmit={handleSubmit}
          onDefault={handleDefault}
          busy={busy}
          message={message}
          error={error}
        />
      </main>
    );
  }

  return (
    <WorkspaceFrame active="understand">
      <section className="page-heading page-heading--understand">
        <div>
          <span>理解数据库</span>
          <h1>看清每张表在业务里代表什么</h1>
          <p>可以一次理解整个数据库，也可以在结构变化后单独更新某张表。</p>
        </div>
        <div className="database-stats">
          <div><strong>{snapshot.scan_statistics.table_count}</strong><span>数据表</span></div>
          <div><strong>{snapshot.scan_statistics.column_count}</strong><span>字段</span></div>
          <div><strong>{snapshot.scan_statistics.foreign_key_count}</strong><span>表间关系</span></div>
        </div>
      </section>

      <section className="understand-all">
        <div>
          <strong>理解整个数据库</strong>
          <span>逐表分析结构、样本数据和关联关系，生成一版完整解释。</span>
        </div>
        <button
          type="button"
          onClick={handleBuildCatalog}
          disabled={catalogBuildBusy}
        >
          {catalogBuildBusy ? "正在理解…" : "开始全库理解"}
        </button>
        {catalogBuild && (
          <div className="understand-progress">
            <div><span style={{width: `${progress}%`}} /></div>
            <p>
              已完成 {catalogBuild.processed_tables}/{catalogBuild.total_tables} 张表
              {catalogBuild.current_table ? `，正在处理 ${catalogBuild.current_table}` : ""}
            </p>
          </div>
        )}
        {catalogBuildError && <p className="form-error">{catalogBuildError}</p>}
      </section>

      <div className="understanding-workspace">
        <TableList
          tables={snapshot.tables}
          catalogEntries={catalogEntries}
          selected={selectedTable?.name ?? ""}
          onSelect={selectTable}
        />
        <div className="understanding-detail">
          <div className="workspace-grid">
            {selectedTable && (
              <StructurePanel
                table={selectedTable}
                snapshot={snapshot}
                onUnderstand={() => handleUnderstand()}
                busy={agentBusy}
                error={agentError}
                canResume={Boolean(recoverableRunId)}
                onResume={() => void handleResumeUnderstanding()}
              />
            )}
            {selectedTable && (
              <UnderstandingPanel run={understandingRun} table={selectedTable} />
            )}
          </div>
        </div>
      </div>
    </WorkspaceFrame>
  );
}
