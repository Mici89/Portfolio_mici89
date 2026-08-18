from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.adapters.database import DatabaseAdapterFactory, DatabaseConnectionConfig
from app.adapters.llm import BaseLLMClient, DeepSeekLLMClient
from app.agents.database_action import (
    ConversationIntentRouter,
    DatabaseActionPlanningAgent,
)
from app.agents.database_query import DatabaseQueryAgent
from app.agents.database_understanding import DatabaseUnderstandingAgent
from app.agents.database_understanding.context_builder import UnderstandingContextBuilder
from app.agents.sql_generation import SQLGenerationAgent
from app.core.config import Settings, get_settings
from app.core.exceptions import LLMConfigurationError
from app.graphs.conversation import ConversationGraphRunner
from app.graphs.query import QueryGraphRunner
from app.graphs.understanding import UnderstandingGraphRunner
from app.models import UserPrincipal
from app.repositories.catalog_build_job import (
    CatalogBuildJobRepository,
    FileCatalogBuildJobRepository,
)
from app.repositories.database_action import (
    DatabaseActionRepository,
    FileDatabaseActionRepository,
)
from app.repositories.database_connection import (
    DatabaseConnectionProfileRepository,
    FileDatabaseConnectionProfileRepository,
)
from app.repositories.database_connection.credentials import EncryptedFileCredentialStore
from app.repositories.database_query import (
    DatabaseQueryRunRepository,
    FileDatabaseQueryRunRepository,
)
from app.repositories.database_snapshot import (
    DatabaseSnapshotRepository,
    FileDatabaseSnapshotRepository,
)
from app.repositories.query_session import (
    FileQuerySessionRepository,
    QuerySessionRepository,
)
from app.repositories.semantic_catalog import (
    FileSemanticCatalogRepository,
    SemanticCatalogRepository,
)
from app.repositories.semantic_review import (
    FileSemanticReviewRepository,
    SemanticReviewRepository,
)
from app.repositories.understanding_run import (
    FileUnderstandingRunRepository,
    UnderstandingRunRepository,
)
from app.services.auth import AuthService
from app.services.catalog_build import CatalogBuildService
from app.services.conversation import ConversationService
from app.services.conversation_context import ConversationContextMerger
from app.services.database_action import DatabaseActionService
from app.services.database_connection import DatabaseConnectionService
from app.services.database_query import DatabaseQueryService
from app.services.database_snapshot import DatabaseSnapshotService
from app.services.database_understanding import DatabaseUnderstandingService
from app.services.effective_semantics import EffectiveSemanticResolver
from app.services.query_session import QuerySessionService
from app.services.semantic_catalog import SemanticCatalogService
from app.services.semantic_review import SemanticReviewService

SettingsDependency = Annotated[Settings, Depends(get_settings)]
bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_service(settings: SettingsDependency) -> AuthService:
    return AuthService(
        operator_username=settings.auth_operator_username,
        operator_password=settings.auth_operator_password.get_secret_value(),
        token_secret=settings.auth_token_secret.get_secret_value(),
        token_ttl_minutes=settings.auth_token_ttl_minutes,
    )


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def get_current_user(
    request: Request,
    service: AuthServiceDependency,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> UserPrincipal:
    token = (
        credentials.credentials
        if credentials is not None
        else request.cookies.get("semantica_operator_session")
    )
    return service.authenticate(token)


CurrentUserDependency = Annotated[UserPrincipal, Depends(get_current_user)]


def require_database_operator(
    principal: CurrentUserDependency,
    service: AuthServiceDependency,
) -> UserPrincipal:
    return service.require_operator(principal)


DatabaseOperatorDependency = Annotated[
    UserPrincipal,
    Depends(require_database_operator),
]


@lru_cache
def get_database_adapter_factory() -> DatabaseAdapterFactory:
    return DatabaseAdapterFactory()


DatabaseAdapterFactoryDependency = Annotated[
    DatabaseAdapterFactory,
    Depends(get_database_adapter_factory),
]


def get_default_database_connection_config(
    settings: SettingsDependency,
) -> DatabaseConnectionConfig:
    return DatabaseConnectionConfig(
        database_type=settings.db_type,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        username=settings.db_user,
        password=settings.db_password.get_secret_value(),
        schema_name=settings.db_schema,
        connect_timeout_seconds=settings.db_connect_timeout_seconds,
    )


DefaultDatabaseConnectionConfigDependency = Annotated[
    DatabaseConnectionConfig,
    Depends(get_default_database_connection_config),
]


def get_write_database_connection_config(
    settings: SettingsDependency,
) -> DatabaseConnectionConfig:
    return DatabaseConnectionConfig(
        database_type=settings.db_type,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        username=settings.db_write_user,
        password=settings.db_write_password.get_secret_value(),
        schema_name=settings.db_schema,
        connect_timeout_seconds=settings.db_connect_timeout_seconds,
    )


WriteDatabaseConnectionConfigDependency = Annotated[
    DatabaseConnectionConfig,
    Depends(get_write_database_connection_config),
]


def get_database_connection_profile_repository(
    settings: SettingsDependency,
) -> DatabaseConnectionProfileRepository:
    return FileDatabaseConnectionProfileRepository(settings.connection_profile_storage_dir)


DatabaseConnectionProfileRepositoryDependency = Annotated[
    DatabaseConnectionProfileRepository,
    Depends(get_database_connection_profile_repository),
]


def get_database_credential_store(
    settings: SettingsDependency,
) -> EncryptedFileCredentialStore:
    return EncryptedFileCredentialStore(
        settings.credential_storage_dir,
        settings.auth_token_secret.get_secret_value(),
    )


DatabaseCredentialStoreDependency = Annotated[
    EncryptedFileCredentialStore,
    Depends(get_database_credential_store),
]


def get_database_connection_service(
    adapter_factory: DatabaseAdapterFactoryDependency,
    profile_repository: DatabaseConnectionProfileRepositoryDependency,
    credential_store: DatabaseCredentialStoreDependency,
    default_config: DefaultDatabaseConnectionConfigDependency,
    default_write_config: WriteDatabaseConnectionConfigDependency,
) -> DatabaseConnectionService:
    return DatabaseConnectionService(
        adapter_factory,
        profile_repository,
        credential_store,
        default_config,
        default_write_config,
    )


DatabaseConnectionServiceDependency = Annotated[
    DatabaseConnectionService,
    Depends(get_database_connection_service),
]


def get_database_snapshot_repository(
    settings: SettingsDependency,
) -> DatabaseSnapshotRepository:
    return FileDatabaseSnapshotRepository(settings.snapshot_storage_dir)


DatabaseSnapshotRepositoryDependency = Annotated[
    DatabaseSnapshotRepository,
    Depends(get_database_snapshot_repository),
]


def get_database_snapshot_service(
    repository: DatabaseSnapshotRepositoryDependency,
    adapter_factory: DatabaseAdapterFactoryDependency,
) -> DatabaseSnapshotService:
    return DatabaseSnapshotService(repository, adapter_factory)


DatabaseSnapshotServiceDependency = Annotated[
    DatabaseSnapshotService,
    Depends(get_database_snapshot_service),
]


def get_llm_client(settings: SettingsDependency) -> BaseLLMClient:
    if settings.deepseek_api_key is None:
        raise LLMConfigurationError()
    api_key = settings.deepseek_api_key.get_secret_value()
    if not api_key:
        raise LLMConfigurationError()
    return DeepSeekLLMClient(
        api_key=api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        timeout_seconds=settings.deepseek_timeout_seconds,
        temperature=settings.deepseek_temperature,
    )


LLMClientDependency = Annotated[BaseLLMClient, Depends(get_llm_client)]


def get_database_understanding_agent(
    llm_client: LLMClientDependency,
    settings: SettingsDependency,
) -> DatabaseUnderstandingAgent:
    sql_generation_agent = SQLGenerationAgent(llm_client)
    return DatabaseUnderstandingAgent(
        llm_client,
        UnderstandingContextBuilder(),
        sql_generation_agent,
        None,
        max_evidence_rounds=settings.understanding_max_evidence_rounds,
    )


DatabaseUnderstandingAgentDependency = Annotated[
    DatabaseUnderstandingAgent,
    Depends(get_database_understanding_agent),
]


def get_understanding_run_repository(
    settings: SettingsDependency,
) -> UnderstandingRunRepository:
    return FileUnderstandingRunRepository(settings.understanding_run_storage_dir)


UnderstandingRunRepositoryDependency = Annotated[
    UnderstandingRunRepository,
    Depends(get_understanding_run_repository),
]


def get_semantic_catalog_repository(
    settings: SettingsDependency,
) -> SemanticCatalogRepository:
    return FileSemanticCatalogRepository(settings.semantic_catalog_storage_dir)


SemanticCatalogRepositoryDependency = Annotated[
    SemanticCatalogRepository,
    Depends(get_semantic_catalog_repository),
]


def get_semantic_catalog_service(
    catalog_repository: SemanticCatalogRepositoryDependency,
    snapshot_repository: DatabaseSnapshotRepositoryDependency,
    run_repository: UnderstandingRunRepositoryDependency,
) -> SemanticCatalogService:
    return SemanticCatalogService(
        catalog_repository,
        snapshot_repository,
        run_repository,
    )


SemanticCatalogServiceDependency = Annotated[
    SemanticCatalogService,
    Depends(get_semantic_catalog_service),
]


def get_semantic_review_repository(
    settings: SettingsDependency,
) -> SemanticReviewRepository:
    return FileSemanticReviewRepository(settings.semantic_review_storage_dir)


SemanticReviewRepositoryDependency = Annotated[
    SemanticReviewRepository,
    Depends(get_semantic_review_repository),
]


def get_semantic_review_service(
    review_repository: SemanticReviewRepositoryDependency,
    catalog_service: SemanticCatalogServiceDependency,
    run_repository: UnderstandingRunRepositoryDependency,
) -> SemanticReviewService:
    return SemanticReviewService(
        review_repository,
        catalog_service,
        run_repository,
    )


SemanticReviewServiceDependency = Annotated[
    SemanticReviewService,
    Depends(get_semantic_review_service),
]


def get_database_query_run_repository(
    settings: SettingsDependency,
) -> DatabaseQueryRunRepository:
    return FileDatabaseQueryRunRepository(settings.database_query_storage_dir)


DatabaseQueryRunRepositoryDependency = Annotated[
    DatabaseQueryRunRepository,
    Depends(get_database_query_run_repository),
]


def get_effective_semantic_resolver(
    catalog_repository: SemanticCatalogRepositoryDependency,
    review_repository: SemanticReviewRepositoryDependency,
) -> EffectiveSemanticResolver:
    return EffectiveSemanticResolver(catalog_repository, review_repository)


EffectiveSemanticResolverDependency = Annotated[
    EffectiveSemanticResolver,
    Depends(get_effective_semantic_resolver),
]


def get_database_query_agent(
    llm_client: LLMClientDependency,
    settings: SettingsDependency,
) -> DatabaseQueryAgent:
    return DatabaseQueryAgent(
        llm_client,
        None,
        max_attempts=settings.database_query_max_attempts,
    )


DatabaseQueryAgentDependency = Annotated[
    DatabaseQueryAgent,
    Depends(get_database_query_agent),
]


def get_query_graph_runner(
    agent: DatabaseQueryAgentDependency,
    connection_service: DatabaseConnectionServiceDependency,
    adapter_factory: DatabaseAdapterFactoryDependency,
    settings: SettingsDependency,
) -> QueryGraphRunner:
    return QueryGraphRunner(
        agent,
        settings.query_graph_checkpoint_path,
        connection_service,
        adapter_factory,
    )


QueryGraphRunnerDependency = Annotated[
    QueryGraphRunner,
    Depends(get_query_graph_runner),
]


def get_database_query_service(
    snapshot_repository: DatabaseSnapshotRepositoryDependency,
    query_repository: DatabaseQueryRunRepositoryDependency,
    semantic_resolver: EffectiveSemanticResolverDependency,
    agent: DatabaseQueryAgentDependency,
    connection_service: DatabaseConnectionServiceDependency,
    adapter_factory: DatabaseAdapterFactoryDependency,
    graph_runner: QueryGraphRunnerDependency,
) -> DatabaseQueryService:
    return DatabaseQueryService(
        snapshot_repository,
        query_repository,
        semantic_resolver,
        agent,
        connection_service,
        adapter_factory,
        graph_runner,
    )


DatabaseQueryServiceDependency = Annotated[
    DatabaseQueryService,
    Depends(get_database_query_service),
]


def get_query_session_repository(
    settings: SettingsDependency,
) -> QuerySessionRepository:
    return FileQuerySessionRepository(settings.query_session_storage_dir)


QuerySessionRepositoryDependency = Annotated[
    QuerySessionRepository,
    Depends(get_query_session_repository),
]


def get_query_session_service(
    session_repository: QuerySessionRepositoryDependency,
    snapshot_repository: DatabaseSnapshotRepositoryDependency,
    query_service: DatabaseQueryServiceDependency,
) -> QuerySessionService:
    return QuerySessionService(
        session_repository,
        snapshot_repository,
        query_service,
    )


QuerySessionServiceDependency = Annotated[
    QuerySessionService,
    Depends(get_query_session_service),
]


def get_database_action_repository(
    settings: SettingsDependency,
) -> DatabaseActionRepository:
    return FileDatabaseActionRepository(settings.database_action_storage_dir)


DatabaseActionRepositoryDependency = Annotated[
    DatabaseActionRepository,
    Depends(get_database_action_repository),
]


def get_database_action_service(
    action_repository: DatabaseActionRepositoryDependency,
    session_repository: QuerySessionRepositoryDependency,
    snapshot_repository: DatabaseSnapshotRepositoryDependency,
    semantic_resolver: EffectiveSemanticResolverDependency,
    llm_client: LLMClientDependency,
    adapter_factory: DatabaseAdapterFactoryDependency,
    connection_service: DatabaseConnectionServiceDependency,
    settings: SettingsDependency,
) -> DatabaseActionService:
    return DatabaseActionService(
        action_repository,
        session_repository,
        snapshot_repository,
        semantic_resolver,
        DatabaseActionPlanningAgent(llm_client),
        connection_service,
        adapter_factory,
        max_affected_rows=settings.database_action_max_affected_rows,
        max_planning_rounds=settings.database_action_max_planning_rounds,
        graph_checkpoint_path=settings.action_graph_checkpoint_path,
    )


DatabaseActionServiceDependency = Annotated[
    DatabaseActionService,
    Depends(get_database_action_service),
]


def get_conversation_service(
    llm_client: LLMClientDependency,
    query_session_service: QuerySessionServiceDependency,
    database_action_service: DatabaseActionServiceDependency,
    settings: SettingsDependency,
) -> ConversationService:
    router = ConversationIntentRouter(llm_client)
    context_merger = ConversationContextMerger()
    graph_runner = ConversationGraphRunner(
        router,
        context_merger,
        query_session_service,
        database_action_service,
        settings.conversation_graph_checkpoint_path,
    )
    return ConversationService(
        router,
        context_merger,
        query_session_service,
        database_action_service,
        graph_runner,
    )


ConversationServiceDependency = Annotated[
    ConversationService,
    Depends(get_conversation_service),
]


def get_catalog_build_job_repository(
    settings: SettingsDependency,
) -> CatalogBuildJobRepository:
    return FileCatalogBuildJobRepository(settings.catalog_build_job_storage_dir)


CatalogBuildJobRepositoryDependency = Annotated[
    CatalogBuildJobRepository,
    Depends(get_catalog_build_job_repository),
]


def get_database_understanding_service(
    snapshot_repository: DatabaseSnapshotRepositoryDependency,
    run_repository: UnderstandingRunRepositoryDependency,
    agent: DatabaseUnderstandingAgentDependency,
    catalog_service: SemanticCatalogServiceDependency,
    connection_service: DatabaseConnectionServiceDependency,
    adapter_factory: DatabaseAdapterFactoryDependency,
    settings: SettingsDependency,
) -> DatabaseUnderstandingService:
    graph_runner = UnderstandingGraphRunner(
        agent,
        settings.understanding_graph_checkpoint_path,
        connection_service,
        adapter_factory,
    )
    return DatabaseUnderstandingService(
        snapshot_repository,
        run_repository,
        agent,
        catalog_service,
        connection_service,
        adapter_factory,
        graph_runner,
    )


DatabaseUnderstandingServiceDependency = Annotated[
    DatabaseUnderstandingService,
    Depends(get_database_understanding_service),
]


def get_catalog_build_service(
    job_repository: CatalogBuildJobRepositoryDependency,
    snapshot_repository: DatabaseSnapshotRepositoryDependency,
    understanding_service: DatabaseUnderstandingServiceDependency,
    catalog_service: SemanticCatalogServiceDependency,
) -> CatalogBuildService:
    return CatalogBuildService(
        job_repository,
        snapshot_repository,
        understanding_service,
        catalog_service,
    )


CatalogBuildServiceDependency = Annotated[
    CatalogBuildService,
    Depends(get_catalog_build_service),
]
