from fastapi import APIRouter, HTTPException, Request, Response
from typing import Literal

from pydantic import BaseModel, EmailStr, Field

from customer_service.bootstrap.config import Settings
from customer_service.modules.audit.service import AuditStore
from customer_service.modules.auth.service import AuthService


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class IdentityView(BaseModel):
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    role: str


RoleName = Literal["owner", "admin", "editor", "agent", "viewer"]


class UserView(BaseModel):
    id: str
    tenant_id: str
    email: str
    display_name: str
    role: str
    status: str
    created_at: str


class UserCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(min_length=1, max_length=100)
    role: RoleName


class UserUpdate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=64)
    role: RoleName | None = None
    status: Literal["active", "inactive"] | None = None


def build_router(auth: AuthService, audit: AuditStore, settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["企业认证"])

    @router.post("/login", response_model=IdentityView)
    def login(payload: LoginRequest, request: Request, response: Response) -> IdentityView:
        identity = auth.authenticate(payload.email, payload.password)
        if identity is None:
            raise HTTPException(status_code=401, detail="邮箱或密码错误")
        response.set_cookie(
            "access_token", auth.create_token(identity), httponly=True,
            secure=settings.auth_cookie_secure, samesite="lax", max_age=settings.auth_access_token_minutes * 60,
        )
        audit.add(identity.tenant_id, identity.user_id, "auth.login", "/api/v1/auth/login", "success", request.client.host if request.client else "unknown")
        return IdentityView(**identity.__dict__)

    @router.get("/me", response_model=IdentityView)
    def me(request: Request) -> IdentityView:
        identity = getattr(request.state, "identity", None)
        if identity is None:
            raise HTTPException(status_code=401, detail="未登录")
        return IdentityView(**identity.__dict__)

    @router.post("/logout", status_code=204)
    def logout(response: Response) -> Response:
        response.delete_cookie("access_token")
        response.status_code = 204
        return response

    @router.get("/users", response_model=list[UserView])
    def list_users(tenant_id: str) -> list[UserView]:
        return [UserView.model_validate(item, from_attributes=True) for item in auth.list_users(tenant_id)]

    @router.post("/users", response_model=UserView, status_code=201)
    def create_user(payload: UserCreate) -> UserView:
        try:
            user = auth.create_user(
                payload.tenant_id, payload.email, payload.password,
                payload.display_name, payload.role,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return UserView.model_validate(user, from_attributes=True)

    @router.patch("/users/{user_id}", response_model=UserView)
    def update_user(user_id: str, payload: UserUpdate) -> UserView:
        user = auth.update_user(payload.tenant_id, user_id, payload.role, payload.status)
        if user is None:
            raise HTTPException(status_code=404, detail="成员不存在或无权访问")
        return UserView.model_validate(user, from_attributes=True)

    return router
