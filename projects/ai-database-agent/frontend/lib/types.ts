export type DatabaseType = "mysql" | "postgresql" | "sqlserver" | "oracle";

export type WorkflowStatus = {
  workflow_id: string;
  workflow_kind: "understanding" | "query" | "action" | "conversation";
  status: "running" | "interrupted" | "failed" | "completed";
  current_node: string | null;
  completed_nodes: string[];
  retry_count: number;
  can_resume: boolean;
  awaiting_input: boolean;
  interrupt_payload: unknown;
  error: string | null;
};

export type ConnectionConfig = {
  database_type: DatabaseType;
  host: string;
  port: number;
  database: string;
  username: string;
  password: string;
  schema_name?: string | null;
  connect_timeout_seconds: number;
};

export type ConnectionInfo = {
  status: "connected";
  connection_id: string | null;
  database_type: DatabaseType;
  host: string;
  port: number;
  database: string;
  server_version: string;
  current_user: string;
  latency_ms: number;
};

export type ColumnSchema = {
  name: string;
  ordinal_position: number;
  data_type: string;
  column_type: string;
  nullable: boolean;
  default: unknown;
  comment: string;
  is_primary_key: boolean;
  is_unique: boolean;
};

export type TableSchema = {
  name: string;
  table_type: string;
  comment: string;
  engine: string | null;
  estimated_row_count: number | null;
  primary_key: string[];
  columns: ColumnSchema[];
};

export type DeclaredRelationship = {
  constraint_name: string;
  source_table: string;
  source_columns: string[];
  target_table: string;
  target_columns: string[];
  on_update: string;
  on_delete: string;
};

export type DatabaseSnapshot = {
  snapshot_id: string;
  captured_at: string;
  source: {
    connection_id: string | null;
    database_type: DatabaseType;
    host: string;
    port: number;
    database: string;
    schema_name: string | null;
  };
  database: {
    name: string;
    server_version: string;
    current_user: string;
    character_set: string;
    collation: string;
  };
  tables: TableSchema[];
  declared_relationships: DeclaredRelationship[];
  scan_statistics: {
    table_count: number;
    view_count: number;
    column_count: number;
    foreign_key_count: number;
    index_count: number;
  };
};

export type SemanticCandidate = {
  meaning: string;
  description: string;
  confidence: number;
  supporting_evidence: string[];
  counter_evidence: string[];
};

export type ColumnUnderstanding = {
  column_name: string;
  status: "inferred" | "ambiguous" | "unknown";
  role_candidates: SemanticCandidate[];
  meaning_candidates: SemanticCandidate[];
  sensitivity_candidates: SemanticCandidate[];
};

export type EvidenceRequest = {
  request_type: string;
  target_columns: string[];
  reason: string;
  priority: "high" | "medium" | "low";
};

export type EvidenceStep = {
  round_number: number;
  request: EvidenceRequest;
  query: {
    request_index: number;
    purpose: string;
    sql: string;
  };
  result: {
    status: "executed" | "rejected" | "failed";
    statement_type: string;
    columns: string[];
    rows: Array<Record<string, unknown>>;
    returned_row_count: number;
    truncated: boolean;
    error: string | null;
  };
};

export type UnderstandingRun = {
  run_id: string;
  snapshot_id: string;
  table_name: string;
  created_at: string;
  provider: string;
  model: string;
  prompt_version: string;
  workflow_engine: "legacy" | "langgraph";
  workflow_thread_id: string | null;
  evidence_scope:
    | "schema_only"
    | "schema_and_profile"
    | "schema_and_query_evidence";
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  analysis: {
    summary: string;
    status: "inferred" | "ambiguous" | "unknown";
    table_candidates: SemanticCandidate[];
    table_role_candidates: SemanticCandidate[];
    grain_candidates: SemanticCandidate[];
    columns: ColumnUnderstanding[];
    evidence_requests: EvidenceRequest[];
    limitations: string[];
  };
  evidence_steps: EvidenceStep[];
  completion_status: "completed" | "best_effort";
  termination_reason:
    | "schema_sufficient"
    | "evidence_resolved"
    | "round_limit_reached"
    | "sql_generation_stalled"
    | "evidence_loop_unavailable";
  evidence_round_count: number;
  max_evidence_rounds: number;
  deferred_evidence_requests: EvidenceRequest[];
  catalog_entry_id: string | null;
  catalog_version: number | null;
};

export type CatalogBuildJob = {
  job_id: string;
  snapshot_id: string;
  database_name: string;
  status: "queued" | "running" | "completed" | "partial_failed";
  created_at: string;
  updated_at: string;
  current_table: string | null;
  total_tables: number;
  processed_tables: number;
  completed_tables: number;
  skipped_tables: number;
  failed_tables: number;
  items: Array<{
    table_name: string;
    status: "pending" | "running" | "completed" | "skipped" | "failed";
    run_id: string | null;
    catalog_entry_id: string | null;
    catalog_version: number | null;
    error: string | null;
  }>;
};

export type SemanticCatalogEntry = {
  catalog_entry_id: string;
  version: number;
  status: "active";
  database_name: string;
  connection_id: string | null;
  table_name: string;
  schema_fingerprint: string;
  snapshot_id: string;
  source_run_id: string;
  first_published_at: string;
  published_at: string;
  completion_status: "completed" | "best_effort";
  termination_reason: UnderstandingRun["termination_reason"];
  prompt_version: string;
  provider: string;
  model: string;
  evidence_summary: {
    database_query_rounds: number;
    generated_query_count: number;
    executed_query_count: number;
    rejected_query_count: number;
    failed_query_count: number;
  };
  declared_relationships: DeclaredRelationship[];
  analysis: UnderstandingRun["analysis"];
};

export type CatalogEvidenceBundle = {
  catalog_entry_id: string;
  catalog_version: number;
  table_name: string;
  source_run_id: string;
  generated_at: string;
  declared_relationships: DeclaredRelationship[];
  evidence_steps: EvidenceStep[];
};

export type FieldReviewInput = {
  column_name: string;
  reviewed_meaning: string;
  reviewed_description: string;
  source_candidate_index: number | null;
  note: string;
};

export type CatalogReviewCreate = {
  source_catalog_version: number;
  scope: "table" | "fields";
  reviewer: string;
  table_decision: {
    reviewed_meaning: string;
    reviewed_summary: string;
    source_candidate_index: number | null;
    note: string;
  } | null;
  field_decisions: FieldReviewInput[];
  note: string;
};

export type CatalogReviewRevision = {
  review_id: string;
  catalog_entry_id: string;
  database_name: string;
  table_name: string;
  source_catalog_version: number;
  revision: number;
  display_version: string;
  schema_fingerprint: string;
  created_at: string;
  reviewer: string;
  scope: "table" | "fields";
  status: "partially_reviewed" | "fully_reviewed";
  reviewed_field_count: number;
  total_field_count: number;
  submitted_field_names: string[];
  table_decision: {
    decision: "confirmed" | "edited";
    original_meaning: string;
    original_summary: string;
    reviewed_meaning: string;
    reviewed_summary: string;
    source_candidate_index: number | null;
    note: string;
  } | null;
  field_decisions: Array<{
    column_name: string;
    decision: "confirmed" | "edited";
    original_meaning: string;
    original_description: string;
    reviewed_meaning: string;
    reviewed_description: string;
    source_candidate_index: number | null;
    note: string;
  }>;
  note: string;
  reviewed_analysis: UnderstandingRun["analysis"];
};

export type DatabaseQueryRun = {
  query_id: string;
  snapshot_id: string;
  database_name: string;
  question: string;
  created_at: string;
  status: "completed" | "execution_failed";
  workflow_engine: "legacy" | "langgraph";
  workflow_thread_id: string | null;
  provider: string;
  model: string;
  usage: UnderstandingRun["usage"];
  semantic_sources: Array<{
    table_name: string;
    catalog_version: number | null;
    review_version: string | null;
    source: "reviewed" | "ai_catalog" | "schema_only";
  }>;
  attempts: Array<{
    attempt_number: number;
    plan: {
      plan_type: "answer" | "evidence";
      intent: {
        summary: string;
        metrics: string[];
        dimensions: string[];
        filters: string[];
        detail_requests: string[];
        tables: string[];
        field_mappings: Array<{
          user_term: string;
          table_name: string;
          column_name: string;
          semantic_meaning: string;
          source: "reviewed" | "ai_catalog" | "schema_only";
          reason: string;
        }>;
        assumptions: string[];
      };
      sql: string;
      sql_purpose: string;
      expected_columns: string[];
    };
    result: EvidenceStep["result"];
    assessment: {
      verdict: "sufficient" | "replan";
      confidence: number;
      reason: string;
      issues: string[];
      next_action: string;
    } | null;
  }>;
  explanation: {
    answer: string;
    observations: string[];
    data_scope: string;
    limitations: string[];
  };
};

export type QuerySessionTurn = {
  turn_id: string;
  parent_turn_id: string | null;
  query_id: string;
  created_at: string;
  user_message: string;
  context_resolution: ConversationContextResolution | null;
  status: "completed" | "execution_failed";
  intent: DatabaseQueryRun["attempts"][number]["plan"]["intent"];
  sql: string;
  result_digest: {
    columns: string[];
    row_count: number;
    sample_rows: Array<Record<string, unknown>>;
    truncated: boolean;
  };
  result_rows: Array<Record<string, unknown>>;
  answer: string;
  observations: string[];
  limitations: string[];
  semantic_sources: DatabaseQueryRun["semantic_sources"];
  attempts: DatabaseQueryRun["attempts"];
};

export type ConversationContextResolution = {
  mode: "standalone" | "refine" | "switch";
  reason: string;
  inherited_metrics: string[];
  inherited_dimensions: string[];
  inherited_filters: string[];
  inherited_tables: string[];
  added_metrics: string[];
  added_dimensions: string[];
  added_filters: string[];
  detail_requests: string[];
  required_metrics: string[];
  required_dimensions: string[];
  required_filters: string[];
  required_tables: string[];
};

export type QuerySession = {
  session_id: string;
  snapshot_id: string;
  database_name: string;
  connection_id: string | null;
  title: string;
  created_at: string;
  updated_at: string;
  active_turn_id: string | null;
  current_intent: DatabaseQueryRun["attempts"][number]["plan"]["intent"] | null;
  pending_query: {
    query_id: string;
    message: string;
    created_at: string;
    context_resolution: ConversationContextResolution | null;
  } | null;
  turns: QuerySessionTurn[];
};

export type QuerySessionSummary = {
  session_id: string;
  snapshot_id: string;
  database_name: string;
  connection_id: string | null;
  title: string;
  created_at: string;
  updated_at: string;
  turn_count: number;
};

export type QueryTurnResponse = {
  session: QuerySession;
  turn: QuerySessionTurn;
  run: DatabaseQueryRun;
};

export type DatabaseActionLookupResolution = {
  lookup_id: string;
  purpose: string;
  target_kind: "assignment" | "condition";
  target_column_name: string;
  source_table: string;
  source_value_column: string;
  display_sql: string;
  status: "resolved" | "not_found" | "ambiguous" | "failed";
  matched_row_count: number;
  truncated: boolean;
  rows: Array<Record<string, unknown>>;
  resolved_value: string | number | boolean | null;
  message: string;
};

export type DatabaseActionRecord = {
  action_id: string;
  session_id: string;
  snapshot_id: string;
  database_name: string;
  user_message: string;
  requested_by: string;
  requested_by_role: string;
  confirmed_by: string | null;
  cancelled_by: string | null;
  created_at: string;
  updated_at: string;
  status:
    | "pending_confirmation"
    | "executing"
    | "blocked"
    | "executed"
    | "failed"
    | "recovery_required"
    | "cancelled";
  workflow_engine: "legacy" | "langgraph";
  workflow_thread_id: string | null;
  provider: string;
  model: string;
  usage: UnderstandingRun["usage"];
  draft: {
    summary: string;
    action_type: "INSERT" | "UPDATE" | "DELETE";
    table_name: string;
    assignments: Array<{
      column_name: string;
      value:
        | string
        | number
        | boolean
        | null
        | {lookup_id: string};
      reason: string;
    }>;
    conditions: Array<{
      column_name: string;
      operator: string;
      value:
        | string
        | number
        | boolean
        | null
        | Array<string | number | boolean | null>;
      reason: string;
    }>;
    value_lookups: Array<{
      lookup_id: string;
      purpose: string;
      target_kind: "assignment" | "condition";
      target_column_name: string;
      source_table: string;
      source_value_column: string;
      conditions: Array<{
        column_name: string;
        operator: string;
        value:
          | string
          | number
          | boolean
          | null
          | Array<string | number | boolean | null>;
        reason: string;
      }>;
    }>;
    field_mappings: DatabaseQueryRun["attempts"][number]["plan"]["intent"]["field_mappings"];
    expected_effect: string;
    assumptions: string[];
  };
  parameterized_sql: string;
  sql_parameters: Array<string | number | boolean | null>;
  sql_parameter_values: Record<string, string | number | boolean | null>;
  display_sql: string;
  preview: {
    matched_row_count: number;
    columns: string[];
    sample_rows: Array<Record<string, unknown>>;
    proposed_rows: Array<Record<string, unknown>>;
    truncated: boolean;
  };
  preview_signature: string;
  safety_checks: Array<{
    code: string;
    passed: boolean;
    message: string;
  }>;
  semantic_sources: DatabaseQueryRun["semantic_sources"];
  planning_steps: Array<{
    round_number: number;
    summary: string;
    outcome: "resolved" | "retrying" | "blocked";
    lookup_resolutions: DatabaseActionLookupResolution[];
    message: string;
  }>;
  lookup_resolutions: DatabaseActionLookupResolution[];
  execution: {
    executed_at: string;
    affected_row_count: number;
    verification_passed: boolean;
    before_rows: Array<Record<string, unknown>>;
    after_rows: Array<Record<string, unknown>>;
    message: string;
  } | null;
  error: string | null;
};

export type ConversationMessageResponse = {
  kind: "query" | "action";
  workflow_engine: "legacy" | "langgraph";
  workflow_thread_id: string | null;
  routing: {
    kind: "query" | "action";
    context_mode: "standalone" | "refine" | "switch";
    standalone_intent_complete: boolean;
    confidence: number;
    reason: string;
    omitted_references: string[];
    added_metrics: string[];
    added_dimensions: string[];
    added_filters: string[];
    detail_requests: string[];
    removed_metrics: string[];
    removed_dimensions: string[];
    removed_filters: string[];
    replace_metrics: boolean;
    replace_dimensions: boolean;
    replace_filters: boolean;
  };
  query: QueryTurnResponse | null;
  action: DatabaseActionRecord | null;
};

export type AuthUser = {
  username: string;
  role: "viewer" | "database_operator";
  authenticated: boolean;
  permissions: string[];
};

export type LoginResponse = {
  expires_in_seconds: number;
  user: AuthUser;
};
