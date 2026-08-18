from abc import ABC, abstractmethod

from app.models import DatabaseConnectionProfile


class DatabaseConnectionProfileRepository(ABC):
    @abstractmethod
    def save(self, profile: DatabaseConnectionProfile) -> None:
        """Persist a connection profile without plaintext credentials."""

    @abstractmethod
    def get(self, connection_id: str) -> DatabaseConnectionProfile:
        """Load one connection profile."""

    @abstractmethod
    def list(self) -> list[DatabaseConnectionProfile]:
        """List persisted connection profiles."""
