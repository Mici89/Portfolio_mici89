import uuid
import hashlib
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import get_settings


@dataclass(frozen=True)
class StoredFile:
    path: Path
    size: int
    content_hash: str


class FileTooLargeError(ValueError):
    pass


async def save_upload_file(
    file: UploadFile,
    knowledge_base_id: uuid.UUID,
) -> StoredFile:
    settings = get_settings()

    target_directory = settings.storage_dir / str(knowledge_base_id)
    target_directory.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "").suffix.lower()
    target_path = target_directory / f"{uuid.uuid4()}{suffix}"

    total_size = 0
    hasher = hashlib.sha256()

    try:
        with target_path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                total_size += len(chunk)

                if total_size > settings.max_upload_size:
                    raise FileTooLargeError
                hasher.update(chunk)
                output.write(chunk)
    except Exception:
        target_path.unlink(missing_ok=True)
        raise

    return StoredFile(
        path=target_path,
        size=total_size,
        content_hash=hasher.hexdigest(),
    )