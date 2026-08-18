import base64
import hashlib
import hmac
import json
import time

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.models import LoginResponse, UserPrincipal

VIEWER_PERMISSIONS = ["database:query"]
OPERATOR_PERMISSIONS = [
    "database:query",
    "database_action:plan",
    "database_action:execute",
]


class AuthService:
    def __init__(
        self,
        *,
        operator_username: str,
        operator_password: str,
        token_secret: str,
        token_ttl_minutes: int,
    ) -> None:
        self.operator_username = operator_username
        self.operator_password = operator_password
        self.token_secret = token_secret.encode("utf-8")
        self.token_ttl_seconds = token_ttl_minutes * 60

    @staticmethod
    def anonymous() -> UserPrincipal:
        return UserPrincipal(
            username="anonymous",
            role="viewer",
            authenticated=False,
            permissions=VIEWER_PERMISSIONS,
        )

    def login(self, username: str, password: str) -> tuple[LoginResponse, str]:
        valid_username = hmac.compare_digest(username, self.operator_username)
        valid_password = hmac.compare_digest(password, self.operator_password)
        if not valid_username or not valid_password:
            raise AuthenticationError("用户名或密码错误")
        user = UserPrincipal(
            username=self.operator_username,
            role="database_operator",
            authenticated=True,
            permissions=OPERATOR_PERMISSIONS,
        )
        return (
            LoginResponse(
                expires_in_seconds=self.token_ttl_seconds,
                user=user,
            ),
            self._issue_token(user),
        )

    def authenticate(self, token: str | None) -> UserPrincipal:
        if not token:
            return self.anonymous()
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            expected_signature = self._sign(encoded_payload)
            if not hmac.compare_digest(encoded_signature, expected_signature):
                raise ValueError
            payload = json.loads(self._decode(encoded_payload))
            if int(payload["exp"]) <= int(time.time()):
                raise AuthenticationError("登录已过期，请重新登录")
            if payload["sub"] != self.operator_username:
                raise ValueError
        except AuthenticationError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            raise AuthenticationError("登录凭证无效，请重新登录") from None
        return UserPrincipal(
            username=self.operator_username,
            role="database_operator",
            authenticated=True,
            permissions=OPERATOR_PERMISSIONS,
        )

    @staticmethod
    def require_operator(principal: UserPrincipal) -> UserPrincipal:
        if principal.role != "database_operator" or not principal.authenticated:
            raise AuthorizationError("该操作需要数据库操作员权限")
        return principal

    def _issue_token(self, user: UserPrincipal) -> str:
        payload = {
            "sub": user.username,
            "role": user.role,
            "exp": int(time.time()) + self.token_ttl_seconds,
        }
        encoded_payload = self._encode(json.dumps(payload, separators=(",", ":"), sort_keys=True))
        return f"{encoded_payload}.{self._sign(encoded_payload)}"

    def _sign(self, encoded_payload: str) -> str:
        digest = hmac.new(
            self.token_secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return self._encode_bytes(digest)

    @staticmethod
    def _encode(value: str) -> str:
        return AuthService._encode_bytes(value.encode("utf-8"))

    @staticmethod
    def _encode_bytes(value: bytes) -> str:
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")

    @staticmethod
    def _decode(value: str) -> str:
        padding = "=" * (-len(value) % 4)
        return base64.urlsafe_b64decode(value + padding).decode("utf-8")
