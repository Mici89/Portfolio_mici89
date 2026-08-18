import re
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar
from uuid import uuid4

from pydantic import BaseModel

from app.core.exceptions import ApplicationError

ModelType = TypeVar("ModelType", bound=BaseModel)
RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class JsonModelFileStore:
    def __init__(
        self,
        storage_directory: Path,
        not_found_factory: Callable[[str], ApplicationError],
    ) -> None:
        self.storage_directory = storage_directory
        self.not_found_factory = not_found_factory

    def save(self, resource_id: str, model: BaseModel) -> None:
        self.storage_directory.mkdir(parents=True, exist_ok=True)
        target = self._path_for(resource_id)
        temporary = self.storage_directory / f".{resource_id}.{uuid4().hex}.tmp"
        try:
            temporary.write_text(model.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)

    def get(self, resource_id: str, model_type: type[ModelType]) -> ModelType:
        path = self._path_for(resource_id)
        if not path.is_file():
            raise self.not_found_factory(resource_id)
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self, model_type: type[ModelType]) -> list[ModelType]:
        if not self.storage_directory.is_dir():
            return []
        return [
            model_type.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(self.storage_directory.glob("*.json"))
            if not path.name.startswith(".")
        ]

    def _path_for(self, resource_id: str) -> Path:
        if RESOURCE_ID_PATTERN.fullmatch(resource_id) is None:
            raise self.not_found_factory(resource_id)
        return self.storage_directory / f"{resource_id}.json"
