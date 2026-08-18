import type {
  CatalogEvidenceBundle,
  CatalogBuildJob,
  CatalogReviewCreate,
  CatalogReviewRevision,
  ConnectionConfig,
  ConnectionInfo,
  ConversationMessageResponse,
  AuthUser,
  DatabaseActionRecord,
  DatabaseSnapshot,
  LoginResponse,
  DatabaseQueryRun,
  QuerySession,
  QuerySessionSummary,
  QueryTurnResponse,
  SemanticCatalogEntry,
  UnderstandingRun,
  WorkflowStatus,
} from "./types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly code: string | undefined,
    readonly status: number,
    readonly workflowId?: string,
    readonly workflowKind?: string,
  ) {
    super(message);
    this.name = "ApiRequestError";
  }
}

type ApiErrorBody = {
  error?: {
    code?: string;
    message?: string;
    workflow_id?: string;
    workflow_kind?: string;
  };
  detail?: string | Array<{ msg?: string }>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let body: ApiErrorBody = {};
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // Preserve a useful fallback when a proxy returns a non-JSON error.
    }
    const validationMessage = Array.isArray(body.detail)
      ? body.detail[0]?.msg
      : body.detail;
    throw new ApiRequestError(
      body.error?.message ?? validationMessage ?? `请求失败（${response.status}）`,
      body.error?.code,
      response.status,
      body.error?.workflow_id,
      body.error?.workflow_kind,
    );
  }
  return (await response.json()) as T;
}

export function friendlyApiError(error: unknown, fallback: string): string {
  if (!(error instanceof ApiRequestError)) {
    return error instanceof Error ? "请求暂时失败，请稍后重试。" : fallback;
  }
  if (error.code === "permission_denied") return "当前账号没有执行此操作的权限。";
  if (error.code?.startsWith("database_") || error.code === "snapshot_connection_mismatch") {
    return "数据库暂时无法完成这次操作，请检查连接或重新扫描结构。";
  }
  if (error.code?.startsWith("llm_")) return "模型暂时没有给出可用结果，请保留当前问题并重试。";
  if (error.code?.startsWith("workflow_")) return "本轮处理被中断，已保留可恢复状态，请点击恢复或重新发送。";
  return "这次请求没有完成，请稍后重试。";
}

export async function loginDatabaseOperator(
  username: string,
  password: string,
): Promise<LoginResponse> {
  const response = await request<LoginResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify({username, password}),
  });
  return response;
}

export function getCurrentUser(): Promise<AuthUser> {
  return request("/api/v1/auth/me");
}

export function logoutDatabaseOperator(): Promise<AuthUser> {
  return request("/api/v1/auth/logout", {method: "POST"});
}

export function testConnection(
  connection: ConnectionConfig,
): Promise<ConnectionInfo> {
  return request("/api/v1/database-connections/test", {
    method: "POST",
    body: JSON.stringify(connection),
  });
}

export function connectDatabase(
  connection: ConnectionConfig,
): Promise<ConnectionInfo> {
  return request("/api/v1/database-connections/connect", {
    method: "POST",
    body: JSON.stringify(connection),
  });
}

export function testDefaultConnection(): Promise<ConnectionInfo> {
  return request("/api/v1/database-connections/default/health");
}

export function scanDatabase(
  connection: ConnectionConfig,
): Promise<DatabaseSnapshot> {
  return request("/api/v1/database-snapshots/scan", {
    method: "POST",
    body: JSON.stringify(connection),
  });
}

export function scanSavedConnection(
  connectionId: string,
): Promise<DatabaseSnapshot> {
  return request(
    `/api/v1/database-snapshots/connections/${encodeURIComponent(connectionId)}/scan`,
    {method: "POST"},
  );
}

export function scanDefaultDatabase(): Promise<DatabaseSnapshot> {
  return request("/api/v1/database-snapshots/default/scan", {
    method: "POST",
  });
}

export function understandTable(
  snapshotId: string,
  tableName: string,
): Promise<UnderstandingRun> {
  return request(
    `/api/v1/database-understanding/snapshots/${encodeURIComponent(snapshotId)}/tables/${encodeURIComponent(tableName)}`,
    { method: "POST" },
  );
}

export function getUnderstandingWorkflow(
  runId: string,
): Promise<WorkflowStatus> {
  return request(
    `/api/v1/database-understanding/runs/${encodeURIComponent(runId)}/workflow`,
  );
}

export function resumeUnderstandingRun(
  runId: string,
): Promise<UnderstandingRun> {
  return request(
    `/api/v1/database-understanding/runs/${encodeURIComponent(runId)}/resume`,
    {method: "POST"},
  );
}

export function startCatalogBuild(
  snapshotId: string,
): Promise<CatalogBuildJob> {
  return request(
    `/api/v1/database-understanding/snapshots/${encodeURIComponent(snapshotId)}/catalog-builds`,
    { method: "POST" },
  );
}

export function getCatalogBuild(jobId: string): Promise<CatalogBuildJob> {
  return request(
    `/api/v1/database-understanding/catalog-builds/${encodeURIComponent(jobId)}`,
  );
}

export function listSemanticCatalog(
  databaseName: string,
  connectionId: string | null,
): Promise<SemanticCatalogEntry[]> {
  return request(
    `/api/v1/semantic-catalog/databases/${encodeURIComponent(databaseName)}/tables?connection_id=${encodeURIComponent(connectionId ?? "")}`,
  );
}

export function listLatestCatalogReviews(
  databaseName: string,
  connectionId: string | null,
): Promise<CatalogReviewRevision[]> {
  return request(
    `/api/v1/semantic-catalog/databases/${encodeURIComponent(databaseName)}/reviews?connection_id=${encodeURIComponent(connectionId ?? "")}`,
  );
}

export function getCatalogEvidence(
  databaseName: string,
  tableName: string,
  connectionId: string | null,
): Promise<CatalogEvidenceBundle> {
  return request(
    `/api/v1/semantic-catalog/databases/${encodeURIComponent(databaseName)}/tables/${encodeURIComponent(tableName)}/evidence?connection_id=${encodeURIComponent(connectionId ?? "")}`,
  );
}

export function createCatalogReview(
  databaseName: string,
  tableName: string,
  payload: CatalogReviewCreate,
  connectionId: string | null,
): Promise<CatalogReviewRevision> {
  return request(
    `/api/v1/semantic-catalog/databases/${encodeURIComponent(databaseName)}/tables/${encodeURIComponent(tableName)}/reviews?connection_id=${encodeURIComponent(connectionId ?? "")}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export function queryDatabase(
  snapshotId: string,
  question: string,
): Promise<DatabaseQueryRun> {
  return request(
    `/api/v1/database-query/snapshots/${encodeURIComponent(snapshotId)}`,
    {
      method: "POST",
      body: JSON.stringify({question}),
    },
  );
}

export function getQueryWorkflow(queryId: string): Promise<WorkflowStatus> {
  return request(
    `/api/v1/database-query/runs/${encodeURIComponent(queryId)}/workflow`,
  );
}

export function resumeDatabaseQuery(
  queryId: string,
): Promise<DatabaseQueryRun> {
  return request(
    `/api/v1/database-query/runs/${encodeURIComponent(queryId)}/resume`,
    {method: "POST"},
  );
}

export function createQuerySession(snapshotId: string): Promise<QuerySession> {
  return request("/api/v1/database-query/sessions", {
    method: "POST",
    body: JSON.stringify({snapshot_id: snapshotId}),
  });
}

export function listQuerySessions(
  databaseName: string,
  connectionId: string | null,
): Promise<QuerySessionSummary[]> {
  return request(
    `/api/v1/database-query/sessions?database_name=${encodeURIComponent(databaseName)}&connection_id=${encodeURIComponent(connectionId ?? "")}`,
  );
}

export function getQuerySession(sessionId: string): Promise<QuerySession> {
  return request(
    `/api/v1/database-query/sessions/${encodeURIComponent(sessionId)}`,
  );
}

export function sendQueryTurn(
  sessionId: string,
  message: string,
): Promise<QueryTurnResponse> {
  return request(
    `/api/v1/database-query/sessions/${encodeURIComponent(sessionId)}/turns`,
    {
      method: "POST",
      body: JSON.stringify({message}),
    },
  );
}

export function resumeQueryTurn(
  sessionId: string,
  queryId: string,
): Promise<QueryTurnResponse> {
  return request(
    `/api/v1/database-query/sessions/${encodeURIComponent(sessionId)}/runs/${encodeURIComponent(queryId)}/resume`,
    {method: "POST"},
  );
}

export function sendConversationMessage(
  sessionId: string,
  message: string,
): Promise<ConversationMessageResponse> {
  return request(
    `/api/v1/database-query/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: "POST",
      body: JSON.stringify({message}),
    },
  );
}

export function confirmDatabaseAction(
  actionId: string,
): Promise<DatabaseActionRecord> {
  return request(
    `/api/v1/database-actions/${encodeURIComponent(actionId)}/confirm`,
    {method: "POST"},
  );
}

export function getDatabaseActionWorkflow(
  actionId: string,
): Promise<WorkflowStatus> {
  return request(
    `/api/v1/database-actions/${encodeURIComponent(actionId)}/workflow`,
  );
}

export function cancelDatabaseAction(
  actionId: string,
): Promise<DatabaseActionRecord> {
  return request(
    `/api/v1/database-actions/${encodeURIComponent(actionId)}/cancel`,
    {method: "POST"},
  );
}

export function listDatabaseActions(
  sessionId: string,
): Promise<DatabaseActionRecord[]> {
  return request(
    `/api/v1/database-actions?session_id=${encodeURIComponent(sessionId)}`,
  );
}
