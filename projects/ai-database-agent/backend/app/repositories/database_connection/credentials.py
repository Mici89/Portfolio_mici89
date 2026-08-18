import base64
import hashlib
import os
from contextlib import suppress
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.core.exceptions import DatabaseCredentialNotFoundError


class EncryptedFileCredentialStore:
    def __init__(self, storage_directory: Path, encryption_secret: str) -> None:
        self.storage_directory = storage_directory
        key = base64.urlsafe_b64encode(hashlib.sha256(encryption_secret.encode()).digest())
        self.cipher = Fernet(key)

    def save(self, credential_ref: str, secret: str) -> None:
        self.storage_directory.mkdir(parents=True, exist_ok=True)
        with suppress(OSError):
            os.chmod(self.storage_directory, 0o700)
        target = self.storage_directory / f"{credential_ref}.bin"
        target.write_bytes(self.cipher.encrypt(secret.encode("utf-8")))
        with suppress(OSError):
            os.chmod(target, 0o600)

    def get(self, credential_ref: str) -> str:
        target = self.storage_directory / f"{credential_ref}.bin"
        if not target.is_file():
            raise DatabaseCredentialNotFoundError(credential_ref)
        try:
            return self.cipher.decrypt(target.read_bytes()).decode("utf-8")
        except InvalidToken:
            raise DatabaseCredentialNotFoundError(credential_ref) from None
