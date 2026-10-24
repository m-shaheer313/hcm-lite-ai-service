"""FastAPI dependencies: database session, current user, role guards."""

from collections.abc import Generator
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, Request
from sqlmodel import Session

from app.context import UserContext
from app.errors import AuthError, ForbiddenError
from app.repositories import users as user_repo
from app.security import decode_access_token


def get_db(request: Request) -> Generator[Session]:
    """One database session per request, from the app's engine."""
    with Session(request.app.state.engine) as session:
        yield session


def get_token(request: Request) -> str:
    """Read the Bearer token from the Authorization header."""
    auth = request.headers.get("authorization", "")
    scheme, _, token = auth.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthError("Missing bearer token. Please log in.")
    return token


def get_current_user(
    request: Request,
    token: Annotated[str, Depends(get_token)],
    session: Annotated[Session, Depends(get_db)],
) -> UserContext:
    """Verify the JWT, reload the user from the DB, and build the context.

    Deactivated users (is_active=False) are rejected here, so their old
    tokens stop working immediately.
    """
    try:
        payload = decode_access_token(token, request.app.state.settings.jwt_secret)
        user_id = int(payload["sub"])
    except (pyjwt.PyJWTError, KeyError, ValueError) as exc:
        raise AuthError("Your session is invalid or expired. Please log in again.") from exc

    user = user_repo.get_by_id(session, user_id)
    if user is None or not user.is_active:
        raise AuthError("Your session is no longer valid. Please log in again.")

    return UserContext(
        user_id=user.id,
        role=user.role,
        employee_id=user.employee_id,
        must_change_password=user.must_change_password,
    )


def require_roles(*roles: str):
    """Guard factory: only these roles pass, and only after a password changed."""

    def guard(ctx: Annotated[UserContext, Depends(get_current_user)]) -> UserContext:
        if ctx.must_change_password:
            raise ForbiddenError("You must change your temporary password before using the app.")
        if ctx.role not in roles:
            raise ForbiddenError("Your role is not allowed to do this.")
        return ctx

    return guard
