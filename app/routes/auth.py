"""Auth routes: HTTP only. All logic lives in services/auth_service.py."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from app.config import Settings
from app.context import UserContext
from app.deps import get_current_user, get_db, require_roles
from app.schemas import (
    ChangePasswordRequest,
    HrLoginCreate,
    HrLoginCreated,
    LoginRequest,
    LoginResponse,
    MeResponse,
    OkResponse,
    SetupRequest,
    SetupStatusResponse,
)
from app.security import create_access_token
from app.services import auth_service

router = APIRouter(tags=["auth"])

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[UserContext, Depends(get_current_user)]


@router.get("/setup/status", response_model=SetupStatusResponse)
def setup_status(session: DbSession) -> SetupStatusResponse:
    """Public: is first-run setup still needed? (used by the web page)."""
    return SetupStatusResponse(setup_done=auth_service.setup_status(session))


@router.post("/setup", response_model=LoginResponse)
def setup(body: SetupRequest, request: Request, session: DbSession) -> LoginResponse:
    """First-run: create the Admin + default leave types. Returns 409 after that."""
    settings: Settings = request.app.state.settings
    admin = auth_service.setup(
        session,
        settings,
        email=body.email,
        password=body.password,
        company_name=body.company_name,
    )
    token = create_access_token(
        user_id=admin.id,
        role=admin.role,
        secret=settings.jwt_secret,
        expires_minutes=settings.jwt_expires_minutes,
    )
    return LoginResponse(access_token=token, role=admin.role, must_change_password=False)


@router.post("/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, session: DbSession) -> LoginResponse:
    """Exchange email + password for a JWT."""
    settings: Settings = request.app.state.settings
    result = auth_service.login(session, settings, email=body.email, password=body.password)
    return LoginResponse(**result)


@router.post("/auth/change-password", response_model=OkResponse)
def change_password(
    body: ChangePasswordRequest,
    ctx: CurrentUser,
    session: DbSession,
) -> OkResponse:
    """Change my password. Allowed while must_change_password is still true."""
    auth_service.change_password(
        session, ctx, old_password=body.old_password, new_password=body.new_password
    )
    return OkResponse()


@router.get("/me", response_model=MeResponse)
def me(ctx: CurrentUser, session: DbSession) -> MeResponse:
    """My profile. Also works before the password change is done."""
    return MeResponse(**auth_service.me(session, ctx))


@router.post("/users", response_model=HrLoginCreated)
def create_hr_login(
    body: HrLoginCreate,
    ctx: Annotated[UserContext, Depends(require_roles("admin"))],
    session: DbSession,
) -> HrLoginCreated:
    """Admin creates an HR login. The temporary password is shown ONCE."""
    user, temp_password = auth_service.create_hr_login(session, ctx, email=body.email)
    return HrLoginCreated(email=user.email, temporary_password=temp_password)
