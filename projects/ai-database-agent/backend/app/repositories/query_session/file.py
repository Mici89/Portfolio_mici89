from pathlib import Path

from app.core.exceptions import QuerySessionNotFoundError
from app.models import QuerySession
from app.repositories.json_file import JsonModelFileStore
from app.repositories.query_session.base import QuerySessionRepository


class FileQuerySessionRepository(QuerySessionRepository):
    def __init__(self, storage_directory: Path) -> None:
        self.store = JsonModelFileStore(
            storage_directory,
            QuerySessionNotFoundError,
        )

    def save(self, session: QuerySession) -> None:
        self.store.save(session.session_id, session)

    def get(self, session_id: str) -> QuerySession:
        return self.store.get(session_id, QuerySession)

    def list(self) -> list[QuerySession]:
        return self.store.list(QuerySession)
