from fastapi import APIRouter, Response

from app.api.dependencies import AuthServiceDependency, CurrentUserDependency
from app.models import LoginRequest, LoginResponse, UserPrincipal

router = APIRouter()


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="使用本地数据库操作员账号登录",
)
async def login(
    request: LoginRequest,
    response: Response,
    service: AuthServiceDependency,
) -> LoginResponse:
    login_response, token = service.login(request.username, request.password)
    response.set_cookie(
        key="semantica_operator_session",
        value=token,
        max_age=login_response.expires_in_seconds,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return login_response


@router.get(
    "/me",
    response_model=UserPrincipal,
    summary="读取当前用户与数据库权限",
)
async def me(principal: CurrentUserDependency) -> UserPrincipal:
    return principal


@router.post(
    "/logout",
    response_model=UserPrincipal,
    summary="退出本地数据库操作员会话",
)
async def logout(response: Response) -> UserPrincipal:
    response.delete_cookie(
        key="semantica_operator_session",
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )
    return UserPrincipal(
        username="anonymous",
        role="viewer",
        authenticated=False,
        permissions=["database:query"],
    )
