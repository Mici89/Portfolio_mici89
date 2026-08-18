class ApplicationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        http_status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status_code = http_status_code


class AuthenticationError(ApplicationError):
    def __init__(self, message: str = "需要登录") -> None:
        super().__init__(
            "authentication_required",
            message,
            http_status_code=401,
        )


class AuthorizationError(ApplicationError):
    def __init__(self, message: str = "没有执行该操作的权限") -> None:
        super().__init__(
            "permission_denied",
            message,
            http_status_code=403,
        )


class DatabaseConnectionError(ApplicationError):
    pass


class DatabaseConnectionProfileNotFoundError(ApplicationError):
    def __init__(self, connection_id: str) -> None:
        super().__init__(
            "database_connection_profile_not_found",
            f"数据库连接配置不存在：{connection_id}",
            http_status_code=404,
        )


class DatabaseCredentialNotFoundError(ApplicationError):
    def __init__(self, credential_ref: str) -> None:
        super().__init__(
            "database_credential_not_found",
            f"数据库连接凭据不存在或无法解密：{credential_ref}",
            http_status_code=503,
        )


class SnapshotConnectionMismatchError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "snapshot_connection_mismatch",
            "该旧快照没有连接标识，且与默认数据库不一致；请重新连接并扫描后再执行Agent",
            http_status_code=409,
        )


class DatabaseSnapshotNotFoundError(ApplicationError):
    def __init__(self, snapshot_id: str) -> None:
        super().__init__(
            "database_snapshot_not_found",
            f"数据库快照不存在：{snapshot_id}",
            http_status_code=404,
        )


class DatabaseTableNotFoundError(ApplicationError):
    def __init__(self, table_name: str) -> None:
        super().__init__(
            "database_table_not_found",
            f"数据库快照中不存在表：{table_name}",
            http_status_code=404,
        )


class LLMConfigurationError(ApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "llm_not_configured",
            "大模型服务尚未配置",
            http_status_code=503,
        )


class LLMProviderError(ApplicationError):
    def __init__(self, message: str = "大模型服务调用失败") -> None:
        super().__init__(
            "llm_provider_error",
            message,
            http_status_code=502,
        )


class LLMResponseValidationError(ApplicationError):
    def __init__(self, message: str = "大模型返回结果不符合语义协议") -> None:
        super().__init__(
            "llm_response_validation_error",
            message,
            http_status_code=502,
        )


class UnderstandingRunNotFoundError(ApplicationError):
    def __init__(self, run_id: str) -> None:
        super().__init__(
            "understanding_run_not_found",
            f"数据库理解结果不存在：{run_id}",
            http_status_code=404,
        )


class SemanticCatalogEntryNotFoundError(ApplicationError):
    def __init__(self, identifier: str) -> None:
        super().__init__(
            "semantic_catalog_entry_not_found",
            f"语义目录中不存在条目：{identifier}",
            http_status_code=404,
        )


class SemanticReviewNotFoundError(ApplicationError):
    def __init__(self, identifier: str) -> None:
        super().__init__(
            "semantic_review_not_found",
            f"语义审核版本不存在：{identifier}",
            http_status_code=404,
        )


class SemanticReviewValidationError(ApplicationError):
    def __init__(
        self,
        message: str,
        *,
        http_status_code: int = 422,
    ) -> None:
        super().__init__(
            "semantic_review_validation_error",
            message,
            http_status_code=http_status_code,
        )


class CatalogBuildJobNotFoundError(ApplicationError):
    def __init__(self, job_id: str) -> None:
        super().__init__(
            "catalog_build_job_not_found",
            f"全库理解任务不存在：{job_id}",
            http_status_code=404,
        )


class DatabaseQueryRunNotFoundError(ApplicationError):
    def __init__(self, query_id: str) -> None:
        super().__init__(
            "database_query_run_not_found",
            f"数据库查询记录不存在：{query_id}",
            http_status_code=404,
        )


class QuerySessionNotFoundError(ApplicationError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            "query_session_not_found",
            f"查询会话不存在：{session_id}",
            http_status_code=404,
        )


class DatabaseActionNotFoundError(ApplicationError):
    def __init__(self, action_id: str) -> None:
        super().__init__(
            "database_action_not_found",
            f"数据库操作记录不存在：{action_id}",
            http_status_code=404,
        )


class UnsafeDatabaseActionError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(
            "unsafe_database_action",
            message,
            http_status_code=422,
        )


class DatabaseActionStateError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(
            "database_action_state_conflict",
            message,
            http_status_code=409,
        )


class WorkflowCheckpointNotFoundError(ApplicationError):
    def __init__(self, workflow_id: str) -> None:
        super().__init__(
            "workflow_checkpoint_not_found",
            f"工作流断点不存在：{workflow_id}",
            http_status_code=404,
        )


class WorkflowResumeRequiredError(ApplicationError):
    def __init__(
        self,
        workflow_id: str,
        workflow_kind: str,
        message: str,
    ) -> None:
        super().__init__(
            "workflow_resume_required",
            message,
            http_status_code=503,
        )
        self.workflow_id = workflow_id
        self.workflow_kind = workflow_kind


class WorkflowStateError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(
            "workflow_state_conflict",
            message,
            http_status_code=409,
        )
