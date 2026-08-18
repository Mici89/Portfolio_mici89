"use client";

import {
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useState,
} from "react";

import { useDatabaseSession } from "@/components/database-session";
import { WorkspaceFrame } from "@/components/workspace-frame";
import {
  ApiRequestError,
  cancelDatabaseAction,
  confirmDatabaseAction,
  createQuerySession,
  getCurrentUser,
  friendlyApiError,
  getQuerySession,
  listDatabaseActions,
  listQuerySessions,
  loginDatabaseOperator,
  logoutDatabaseOperator,
  resumeQueryTurn,
  sendConversationMessage,
} from "@/lib/api";
import type {
  AuthUser,
  DatabaseActionRecord,
  DatabaseSnapshot,
  QuerySession,
  QuerySessionSummary,
  QuerySessionTurn,
} from "@/lib/types";

const exampleQuestions = [
  "按盘点状态统计盘点记录数量",
  "统计2026年6月各部门的工资发放总额",
  "把员工编号E00001的在职状态改为Y",
];

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return "NULL";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function sourceLabel(source: string): string {
  if (source === "reviewed") return "人工审核";
  if (source === "ai_catalog") return "系统解释";
  return "仅数据库结构";
}

function formatSessionTime(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function DataTable({
  columns,
  rows,
}: {
  columns: string[];
  rows: Array<Record<string, unknown>>;
}) {
  return (
    <div className="query-data-table">
      <table>
        <thead>
          <tr>
            {columns.map((column) => <th key={column}>{column}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column}>{displayValue(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

async function startSession(snapshot: DatabaseSnapshot): Promise<{
  session: QuerySession;
  sessions: QuerySessionSummary[];
}> {
  const saved = await listQuerySessions(
    snapshot.database.name,
    snapshot.source.connection_id,
  );
  const session =
    saved[0]
      ? await getQuerySession(saved[0].session_id)
      : await createQuerySession(snapshot.snapshot_id);
  return {
    session,
    sessions: saved.length ? saved : [sessionSummary(session)],
  };
}

function sessionSummary(session: QuerySession): QuerySessionSummary {
  return {
    session_id: session.session_id,
    snapshot_id: session.snapshot_id,
    database_name: session.database_name,
    connection_id: session.connection_id,
    title: session.title,
    created_at: session.created_at,
    updated_at: session.updated_at,
    turn_count: session.turns.length,
  };
}

function TurnAnswer({turn}: {turn: QuerySessionTurn}) {
  const columns = turn.result_digest.columns;
  const rows = turn.result_rows?.length
    ? turn.result_rows
    : turn.result_digest.sample_rows;
  const resolution = turn.context_resolution;
  return (
    <div className="chat-turn">
      <div className="chat-message chat-message--user">
        <span>你</span>
        <p>{turn.user_message}</p>
      </div>
      <div className="chat-message chat-message--agent">
        <span className="chat-agent-mark">答</span>
        <div className="chat-answer-body">
          <div className="chat-answer-heading">
            <strong>{turn.answer}</strong>
          </div>

          <details className="chat-turn-details" open>
            <summary>
              <span className="chat-turn-details-open">展开详情</span>
              <span className="chat-turn-details-close">收起详情</span>
              <small>
                {turn.result_digest.row_count} 行数据 · {turn.attempts.length} 轮查询
              </small>
            </summary>
            <div className="chat-turn-detail-meta">
              <em className={`query-status query-status--${turn.status}`}>
                {turn.status === "completed" ? "已执行" : "执行失败"}
              </em>
              <code>{turn.query_id}</code>
            </div>

            {turn.observations.length > 0 && (
              <div className="chat-detail-section">
                <span>结果观察</span>
                <ul>
                  {turn.observations.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            )}

            {rows.length > 0 && columns.length > 0 && (
              <div className="chat-detail-section chat-detail-data">
                <div>
                  <span>详细数据</span>
                  <small>
                    {turn.result_digest.row_count} 行
                    {turn.result_digest.truncated ? " · 已截断" : ""}
                  </small>
                </div>
                <DataTable columns={columns} rows={rows} />
              </div>
            )}

            {resolution && (
              <div className="chat-context-resolution">
                <div>
                  <span>上下文处理</span>
                  <strong>
                    {resolution.mode === "refine"
                      ? "延续并细化"
                      : resolution.mode === "switch"
                        ? "切换主题"
                        : "独立问题"}
                  </strong>
                </div>
                <p>{resolution.reason}</p>
                <div>
                  {resolution.inherited_metrics.map((item) => (
                    <em key={`metric-${item}`}>继承指标 · {item}</em>
                  ))}
                  {resolution.inherited_filters.map((item) => (
                    <em key={`filter-${item}`}>继承条件 · {item}</em>
                  ))}
                  {resolution.added_filters.map((item) => (
                    <em key={`added-${item}`}>新增条件 · {item}</em>
                  ))}
                  {resolution.detail_requests.map((item) => (
                    <em key={`detail-${item}`}>展开 · {item}</em>
                  ))}
                </div>
              </div>
            )}

            {turn.attempts.length > 0 && (
              <div className="agent-loop-trace agent-loop-trace--query">
                <div>
                  <span>查询闭环</span>
                  <small>
                    {turn.attempts.length === 1
                      ? "首轮结果通过质检"
                      : `${turn.attempts.length} 轮后收敛`}
                  </small>
                </div>
                <ol>
                  {turn.attempts.map((attempt) => (
                    <li
                      className={
                        attempt.assessment?.verdict === "sufficient"
                          ? "is-resolved"
                          : "is-replanned"
                      }
                      key={attempt.attempt_number}
                    >
                      <i>{attempt.attempt_number}</i>
                      <span>
                        <strong>
                          {attempt.plan.plan_type === "evidence"
                            ? "取证查询"
                            : "回答查询"}
                        </strong>
                        <small>
                          {attempt.result.status === "executed"
                            ? attempt.assessment?.reason ?? "已执行"
                            : attempt.result.error ?? "执行失败"}
                        </small>
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            )}

            <div className="chat-intent-summary">
              <strong>{turn.intent.summary}</strong>
              <div>
                {turn.intent.metrics.map((item) => <em key={item}>指标 · {item}</em>)}
                {turn.intent.dimensions.map((item) => <em key={item}>维度 · {item}</em>)}
                {turn.intent.filters.map((item) => <em key={item}>条件 · {item}</em>)}
                {turn.intent.detail_requests.map((item) => (
                  <em key={item}>详情 · {item}</em>
                ))}
              </div>
            </div>

            <div className="chat-semantic-sources">
              {turn.semantic_sources.map((source) => (
                <span className={`source-${source.source}`} key={source.table_name}>
                  {source.table_name}
                  <small>
                    {source.review_version ??
                      (source.catalog_version
                        ? `v${source.catalog_version}`
                        : "Schema")}
                    {" · "}
                    {sourceLabel(source.source)}
                  </small>
                </span>
              ))}
            </div>

            <div className="chat-field-mappings">
              {turn.intent.field_mappings.map((mapping) => (
                <div
                  key={`${mapping.user_term}-${mapping.table_name}-${mapping.column_name}`}
                >
                  <span>{mapping.user_term}</span>
                  <code>{mapping.table_name}.{mapping.column_name}</code>
                  <small>{sourceLabel(mapping.source)}</small>
                </div>
              ))}
            </div>
            {turn.attempts.length > 1 ? (
              <div className="query-attempt-details">
                {turn.attempts.map((attempt) => (
                  <div key={attempt.attempt_number}>
                    <span>
                      第 {attempt.attempt_number} 轮 ·{" "}
                      {attempt.plan.plan_type === "evidence" ? "取证" : "回答"}
                    </span>
                    <small>{attempt.assessment?.next_action}</small>
                    <pre><code>{attempt.plan.sql}</code></pre>
                  </div>
                ))}
              </div>
            ) : (
              <pre><code>{turn.sql}</code></pre>
            )}

            {turn.limitations.length > 0 && (
              <div className="chat-limitations">
                {turn.limitations.map((item) => <p key={item}>{item}</p>)}
              </div>
            )}
          </details>
        </div>
      </div>
    </div>
  );
}

function actionLabel(actionType: DatabaseActionRecord["draft"]["action_type"]) {
  if (actionType === "INSERT") return "新增记录";
  if (actionType === "UPDATE") return "更新记录";
  return "删除记录";
}

function actionStatusLabel(status: DatabaseActionRecord["status"]) {
  if (status === "pending_confirmation") return "等待确认";
  if (status === "executing") return "事务执行中";
  if (status === "blocked") return "安全检查未通过";
  if (status === "executed") return "已执行并回查";
  if (status === "recovery_required") return "需要人工核对";
  if (status === "cancelled") return "已取消";
  return "执行失败";
}

function lookupStatusLabel(
  status: DatabaseActionRecord["lookup_resolutions"][number]["status"],
) {
  if (status === "resolved") return "唯一匹配";
  if (status === "not_found") return "没有匹配";
  if (status === "ambiguous") return "存在多个候选";
  return "查询失败";
}

function ActionCard({
  action,
  busy,
  onConfirm,
  onCancel,
}: {
  action: DatabaseActionRecord;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const previewRows = action.preview.sample_rows.length
    ? action.preview.sample_rows
    : action.preview.proposed_rows;
  const columns = action.preview.columns.length
    ? action.preview.columns
    : Object.keys(previewRows[0] ?? {});
  const executable = action.status === "pending_confirmation";

  return (
    <div className="chat-turn">
      <div className="chat-message chat-message--user">
        <span>你</span>
        <p>{action.user_message}</p>
      </div>
      <div className="chat-message chat-message--agent">
        <span className="chat-agent-mark chat-agent-mark--action">A</span>
        <div className={`database-action-card action-status--${action.status}`}>
          <header>
            <div>
              <span>Database Action Plan</span>
              <strong>{action.draft.summary}</strong>
            </div>
            <em>{actionStatusLabel(action.status)}</em>
          </header>

          <div className="action-plan-facts">
            <span>
              <small>操作</small>
              {actionLabel(action.draft.action_type)}
            </span>
            <span>
              <small>目标表</small>
              <code>{action.draft.table_name}</code>
            </span>
            <span>
              <small>预计影响</small>
              {action.preview.matched_row_count} 行
            </span>
          </div>

          {action.planning_steps.length > 0 && (
            <div className="agent-loop-trace agent-loop-trace--action">
              <div>
                <span>写操作闭环</span>
                <small>
                  {action.lookup_resolutions.length
                    ? "先查业务值，再生成单表写入"
                    : "直接生成单表写入"}
                </small>
              </div>
              <ol>
                {action.planning_steps.map((step) => (
                  <li
                    className={
                      step.outcome === "resolved" ? "is-resolved" : "is-replanned"
                    }
                    key={step.round_number}
                  >
                    <i>{step.round_number}</i>
                    <span>
                      <strong>
                        {step.outcome === "resolved"
                          ? "规划已收敛"
                          : step.outcome === "retrying"
                            ? "携带证据重规划"
                            : "安全阻止"}
                      </strong>
                      <small>{step.message}</small>
                    </span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {action.lookup_resolutions.length > 0 && (
            <div className="action-lookup-evidence">
              <div>
                <span>跨表取值证据</span>
                <small>只读 SELECT · 不修改来源表</small>
              </div>
              {action.lookup_resolutions.map((lookup) => {
                const lookupColumns = Object.keys(lookup.rows[0] ?? {});
                return (
                  <article
                    className={`lookup-status--${lookup.status}`}
                    key={lookup.lookup_id}
                  >
                    <header>
                      <div>
                        <strong>{lookup.purpose}</strong>
                        <code>
                          {lookup.source_table}.{lookup.source_value_column}
                          {" → "}
                          {action.draft.table_name}.{lookup.target_column_name}
                        </code>
                      </div>
                      <em>{lookupStatusLabel(lookup.status)}</em>
                    </header>
                    <p>{lookup.message}</p>
                    {lookup.rows.length > 0 && (
                      <DataTable columns={lookupColumns} rows={lookup.rows} />
                    )}
                    <details>
                      <summary>查看只读取值 SQL</summary>
                      <pre><code>{lookup.display_sql}</code></pre>
                    </details>
                  </article>
                );
              })}
            </div>
          )}

          {action.draft.assignments.length > 0 && (
            <div className="action-change-list">
              <span>准备写入</span>
              <div>
                {action.draft.assignments.map((assignment) => (
                  <code key={assignment.column_name}>
                    {assignment.column_name} = {displayValue(assignment.value)}
                  </code>
                ))}
              </div>
            </div>
          )}

          {previewRows.length > 0 && (
            <div className="action-preview">
              <div>
                <span>
                  {action.draft.action_type === "INSERT"
                    ? "待新增数据"
                    : "修改前数据预览"}
                </span>
                <small>最多展示 10 行</small>
              </div>
              <DataTable columns={columns} rows={previewRows} />
            </div>
          )}

          <div className="action-safety-checks">
            {action.safety_checks.map((check) => (
              <span className={check.passed ? "passed" : "failed"} key={check.code}>
                <i>{check.passed ? "✓" : "!"}</i>
                {check.message}
              </span>
            ))}
          </div>

          {action.execution && (
            <>
              <div className="action-execution-result">
                <strong>{action.execution.message}</strong>
                <span>
                  回查{action.execution.verification_passed ? "通过" : "失败"}
                  {" · "}
                  {action.execution.after_rows.length} 行结果
                </span>
              </div>
              <details className="action-verification-evidence">
                <summary>查看事务执行前后回查</summary>
                <div>
                  <span>执行前</span>
                  <pre>{JSON.stringify(action.execution.before_rows, null, 2)}</pre>
                </div>
                <div>
                  <span>执行后</span>
                  <pre>{JSON.stringify(action.execution.after_rows, null, 2)}</pre>
                </div>
              </details>
            </>
          )}

          <div className="action-audit-identity">
            <span>申请人 · {action.requested_by}</span>
            {action.confirmed_by && <span>执行确认 · {action.confirmed_by}</span>}
            {action.cancelled_by && <span>取消人 · {action.cancelled_by}</span>}
          </div>

          {action.error && <p className="action-error">{action.error}</p>}

          <details className="chat-query-details">
            <summary>查看条件、字段映射与参数化 SQL</summary>
            <div className="action-condition-list">
              {action.draft.conditions.map((condition) => (
                <code key={`${condition.column_name}-${condition.operator}`}>
                  {condition.column_name} {condition.operator}{" "}
                  {displayValue(condition.value)}
                </code>
              ))}
            </div>
            <div className="chat-field-mappings">
              {action.draft.field_mappings.map((mapping) => (
                <div
                  key={`${mapping.user_term}-${mapping.table_name}-${mapping.column_name}`}
                >
                  <span>{mapping.user_term}</span>
                  <code>{mapping.table_name}.{mapping.column_name}</code>
                  <small>{sourceLabel(mapping.source)}</small>
                </div>
              ))}
            </div>
            <pre><code>{action.display_sql}</code></pre>
          </details>

          {executable && (
            <div className="action-confirmation">
              <div>
                <strong>流程已暂停，等待你的明确确认</strong>
                <span>
                  刷新或重启后仍可继续；确认时会重新核对完整目标行。
                </span>
              </div>
              <button type="button" onClick={onCancel} disabled={busy}>
                取消
              </button>
              <button type="button" onClick={onConfirm} disabled={busy}>
                {busy ? "执行中…" : "确认执行"}
              </button>
            </div>
          )}
          <small className="chat-turn-id">{action.action_id}</small>
        </div>
      </div>
    </div>
  );
}

export function DatabaseQueryWorkspace() {
  const {ready, snapshot} = useDatabaseSession();
  const [session, setSession] = useState<QuerySession | null>(null);
  const [sessions, setSessions] = useState<QuerySessionSummary[]>([]);
  const [actions, setActions] = useState<DatabaseActionRecord[]>([]);
  const [message, setMessage] = useState("");
  const [pendingMessage, setPendingMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [busyActionId, setBusyActionId] = useState("");
  const [error, setError] = useState("");
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authUsername, setAuthUsername] = useState("db_operator");
  const [authPassword, setAuthPassword] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState("");

  const createNewSession = async () => {
    if (!snapshot) return;
    setBusy(true);
    setError("");
    try {
      const next = await createQuerySession(snapshot.snapshot_id);
      setSession(next);
      setSessions((current) => [sessionSummary(next), ...current]);
      setMessage("");
      setPendingMessage("");
      setActions([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "查询会话创建失败");
    } finally {
      setBusy(false);
    }
  };

  const selectSession = async (sessionId: string) => {
    if (sessionId === session?.session_id || busy) return;
    setBusy(true);
    setError("");
    try {
      const next = await getQuerySession(sessionId);
      setSession(next);
      setActions([]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "历史对话读取失败");
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!ready || !snapshot) {
      return;
    }
    let active = true;
    const bootstrap = async () => {
      setLoading(true);
      try {
        const next = await startSession(snapshot);
        if (!active) return;
        setSession(next.session);
        setSessions(next.sessions);
      } catch (caught) {
        if (active) {
          setError(caught instanceof Error ? caught.message : "查询会话创建失败");
        }
      } finally {
        if (active) setLoading(false);
      }
    };
    void bootstrap();
    return () => {
      active = false;
    };
  }, [ready, snapshot]);

  const activeSessionId = session?.session_id;

  useEffect(() => {
    let active = true;
    if (!activeSessionId || authUser?.role !== "database_operator") {
      return () => {
        active = false;
      };
    }
    void listDatabaseActions(activeSessionId)
      .then((records) => {
        if (active) setActions(records);
      })
      .catch(() => {
        if (active) setActions([]);
      });
    return () => {
      active = false;
    };
  }, [activeSessionId, authUser?.role]);

  const rememberSession = (updated: QuerySession) => {
    setSession(updated);
    setSessions((current) => [
      sessionSummary(updated),
      ...current.filter((item) => item.session_id !== updated.session_id),
    ]);
  };

  useEffect(() => {
    let active = true;
    void getCurrentUser()
      .then((user) => {
        if (active) setAuthUser(user);
      })
      .catch(() => {
        if (active) {
          setAuthUser({
            username: "anonymous",
            role: "viewer",
            authenticated: false,
            permissions: ["database:query"],
          });
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const contextChips = useMemo(() => {
    const intent = session?.current_intent;
    if (!intent) return [];
    return [
      ...intent.metrics.map((value) => ({kind: "指标", value})),
      ...intent.dimensions.map((value) => ({kind: "维度", value})),
      ...intent.filters.map((value) => ({kind: "条件", value})),
    ];
  }, [session]);

  const conversationItems = useMemo(() => {
    const queryItems = (session?.turns ?? []).map((turn) => ({
      kind: "query" as const,
      id: turn.turn_id,
      createdAt: turn.created_at,
      turn,
    }));
    const actionItems = actions.map((action) => ({
      kind: "action" as const,
      id: action.action_id,
      createdAt: action.created_at,
      action,
    }));
    return [...queryItems, ...actionItems].sort((left, right) =>
      left.createdAt.localeCompare(right.createdAt),
    );
  }, [actions, session]);

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    if (!session || !message.trim() || busy) return;
    const nextMessage = message.trim();
    setBusy(true);
    setError("");
    setPendingMessage(nextMessage);
    setMessage("");
    try {
      const response = await sendConversationMessage(session.session_id, nextMessage);
      if (response.kind === "query" && response.query) {
        rememberSession(response.query.session);
      } else if (response.action) {
        setActions((current) => [...current, response.action as DatabaseActionRecord]);
        const updated = await getQuerySession(session.session_id);
        rememberSession(updated);
      }
    } catch (caught) {
      if (
        caught instanceof ApiRequestError &&
        caught.code === "permission_denied"
      ) {
        setError(`${friendlyApiError(caught, "查询失败")} 请先在左侧登录。`);
      } else {
        setError(friendlyApiError(caught, "查询失败"));
        if (
          caught instanceof ApiRequestError &&
          caught.workflowKind === "query" &&
          caught.workflowId
        ) {
          try {
            rememberSession(await getQuerySession(session.session_id));
          } catch {
            // The recoverable workflow id remains in the error response.
          }
        }
      }
      setMessage(nextMessage);
    } finally {
      setPendingMessage("");
      setBusy(false);
    }
  };

  const resumePendingQuery = async () => {
    const pending = session?.pending_query;
    if (!session || !pending || busy) return;
    setBusy(true);
    setPendingMessage(pending.message);
    setError("");
    try {
      const response = await resumeQueryTurn(
        session.session_id,
        pending.query_id,
      );
      rememberSession(response.session);
      setMessage("");
    } catch (caught) {
      setError(friendlyApiError(caught, "查询断点恢复失败"));
    } finally {
      setPendingMessage("");
      setBusy(false);
    }
  };

  const signIn = async (event: FormEvent) => {
    event.preventDefault();
    if (!authUsername.trim() || !authPassword || authBusy) return;
    setAuthBusy(true);
    setAuthError("");
    try {
      const response = await loginDatabaseOperator(
        authUsername.trim(),
        authPassword,
      );
      setAuthUser(response.user);
      setAuthPassword("");
      setError("");
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : "登录失败");
    } finally {
      setAuthBusy(false);
    }
  };

  const signOut = async () => {
    try {
      setAuthUser(await logoutDatabaseOperator());
      setAuthPassword("");
      setActions([]);
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : "退出失败");
    }
  };

  const updateAction = async (
    action: DatabaseActionRecord,
    operation: "confirm" | "cancel",
  ) => {
    setBusyActionId(action.action_id);
    setError("");
    try {
      const updated = operation === "confirm"
        ? await confirmDatabaseAction(action.action_id)
        : await cancelDatabaseAction(action.action_id);
      setActions((current) =>
        current.map((item) => item.action_id === updated.action_id ? updated : item),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "数据库操作处理失败");
    } finally {
      setBusyActionId("");
    }
  };

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  return (
    <WorkspaceFrame active="query">
      <section className="chat-query-page">
        <aside className="chat-context-panel">
          <div className="chat-session-meta">
            <span className="eyebrow">当前对话</span>
            <strong>{session?.title ?? "正在建立对话"}</strong>
            <small>{snapshot?.database.name ?? "等待数据库快照"}</small>
            <button
              type="button"
              onClick={() => void createNewSession()}
              disabled={loading || busy || !snapshot}
            >
              ＋ 新对话
            </button>
          </div>

          <div className="chat-history-panel">
            <div>
              <span className="subheading">历史对话</span>
              <small>{sessions.length} 个已保存对话</small>
            </div>
            <nav aria-label="历史对话">
              {sessions.map((item) => (
                <button
                  className={
                    item.session_id === session?.session_id ? "active" : ""
                  }
                  key={item.session_id}
                  onClick={() => void selectSession(item.session_id)}
                  type="button"
                  disabled={busy}
                >
                  <span>{item.title}</span>
                  <small>
                    {item.turn_count} 轮 · {formatSessionTime(item.updated_at)}
                  </small>
                </button>
              ))}
            </nav>
          </div>

          <div className="chat-context-state">
            <span className="subheading">当前分析上下文</span>
            {contextChips.length ? (
              <div>
                {contextChips.map((chip, index) => (
                  <span key={`${chip.kind}-${chip.value}-${index}`}>
                    <small>{chip.kind}</small>
                    {chip.value}
                  </span>
                ))}
              </div>
            ) : (
              <p>第一轮查询完成后，这里会显示当前指标、维度和过滤条件。</p>
            )}
          </div>

          <div className="chat-permission-state">
            <span className="subheading">修改权限</span>
            {authUser?.role === "database_operator" ? (
              <div className="operator-session">
                <span><i /> 已登录数据库操作员</span>
                <strong>{authUser.username}</strong>
                <p>可以生成、确认或取消数据库写操作。</p>
                <button type="button" onClick={() => void signOut()}>
                  退出操作员
                </button>
              </div>
            ) : (
              <form onSubmit={signIn}>
                <p>当前为只读访客，只能执行查询。</p>
                <label>
                  操作员账号
                  <input
                    autoComplete="username"
                    value={authUsername}
                    onChange={(event) => setAuthUsername(event.target.value)}
                  />
                </label>
                <label>
                  密码
                  <input
                    autoComplete="current-password"
                    type="password"
                    value={authPassword}
                    onChange={(event) => setAuthPassword(event.target.value)}
                  />
                </label>
                {authError && <small role="alert">{authError}</small>}
                <button type="submit" disabled={authBusy}>
                  {authBusy ? "验证中…" : "登录以执行写操作"}
                </button>
              </form>
            )}
          </div>
        </aside>

        <section className="chat-main">
          <header className="chat-main-heading">
            <div>
              <span className="eyebrow">智能对话</span>
              <h1>直接问数据库</h1>
            </div>
            <div>
              <strong>{conversationItems.length}</strong>
              <span>轮对话</span>
            </div>
          </header>

          <div className="chat-thread">
            {loading && (
              <div className="query-running">
                <span className="button-loader button-loader--dark" />
                <div>
                  <strong>正在连接数据库并创建会话</strong>
                  <p>会话会固定当前数据库快照。</p>
                </div>
              </div>
            )}

            {!loading && conversationItems.length === 0 && (
              <div className="chat-welcome">
                <span className="chat-agent-mark">答</span>
                <div>
                  <h2>今天想分析什么？</h2>
                  <p>
                    可以查询和连续追问，也可以要求新增、更新或删除业务记录。
                    修改指令会先生成影响预览，只有确认后才执行。
                  </p>
                  <div>
                    {exampleQuestions.map((example) => (
                      <button
                        key={example}
                        type="button"
                        onClick={() => setMessage(example)}
                      >
                        {example}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {conversationItems.map((item) => (
              item.kind === "query"
                ? <TurnAnswer turn={item.turn} key={item.id} />
                : (
                  <ActionCard
                    action={item.action}
                    busy={busyActionId === item.action.action_id}
                    key={item.id}
                    onConfirm={() => void updateAction(item.action, "confirm")}
                    onCancel={() => void updateAction(item.action, "cancel")}
                  />
                )
            ))}

            {busy && (
              <div className="chat-turn chat-turn--pending">
                <div className="chat-message chat-message--user">
                  <span>你</span>
                  <p>{pendingMessage}</p>
                </div>
                <div className="chat-message chat-message--agent">
                  <span className="chat-agent-mark">答</span>
                  <div className="chat-typing">
                    <i /><i /><i />
                    <span>正在识别意图并生成查询或操作计划…</span>
                  </div>
                </div>
              </div>
            )}

            {(error || session?.pending_query) && (
              <div className="chat-workflow-recovery" role="alert">
                <div>
                  <strong>
                    {session?.pending_query
                      ? "查询已保存断点"
                      : "本轮处理失败"}
                  </strong>
                  <span>
                    {error ||
                      "可以从失败节点继续，不会重新执行已经完成的步骤。"}
                  </span>
                </div>
                {session?.pending_query && (
                  <button
                    type="button"
                    onClick={() => void resumePendingQuery()}
                    disabled={busy}
                  >
                    {busy ? "正在恢复…" : "从查询断点继续"}
                  </button>
                )}
              </div>
            )}
          </div>

          <form className="chat-composer" onSubmit={submit}>
            <textarea
              aria-label="输入查询、追问或数据库操作"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={onComposerKeyDown}
              placeholder={
                conversationItems.length
                  ? "继续提问，或输入新增、修改、删除指令"
                  : "输入一个查询或数据库操作"
              }
              rows={2}
              disabled={!session || busy || Boolean(session.pending_query)}
            />
            <button
              type="submit"
              disabled={
                !session ||
                busy ||
                !message.trim() ||
                Boolean(session.pending_query)
              }
            >
              {busy ? "分析中" : "发送"}
              <span>↗</span>
            </button>
            <small>
              Enter 发送 · Shift + Enter 换行 · SELECT 直接执行 · 写操作确认后执行
            </small>
          </form>
        </section>
      </section>
    </WorkspaceFrame>
  );
}
