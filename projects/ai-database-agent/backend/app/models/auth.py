from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

UserRole = Literal["viewer", "database_operator"]


class AuthModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoginRequest(AuthModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=500)


class UserPrincipal(AuthModel):
    username: str
    role: UserRole
    authenticated: bool
    permissions: list[str] = Field(default_factory=list)


class LoginResponse(AuthModel):
    expires_in_seconds: int = Field(gt=0)
    user: UserPrincipal
