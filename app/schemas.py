"""Pydantic models for requests and responses. Strict: extra fields are rejected."""

from pydantic import BaseModel, ConfigDict, Field

from app.services.auth_service import validate_new_password


class StrictModel(BaseModel):
    """Base model: unknown fields are an error, not a silent ignore."""

    model_config = ConfigDict(extra="forbid")


class HealthResponse(BaseModel):
    """Body of GET /health."""

    status: str


class SetupRequest(StrictModel):
    """POST /setup — first run only. Fields optional: env vars are the fallback."""

    email: str | None = None
    password: str | None = None
    company_name: str | None = None


class LoginRequest(StrictModel):
    """POST /auth/login."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=254)


class LoginResponse(BaseModel):
    """Token plus the flags the UI needs right after login."""

    access_token: str
    role: str
    must_change_password: bool


class ChangePasswordRequest(StrictModel):
    """POST /auth/change-password."""

    old_password: str = Field(min_length=1, max_length=254)
    new_password: str = Field(min_length=1, max_length=254)

    def model_post_init(self, __context: object, /) -> None:
        validate_new_password(self.new_password)


class OkResponse(BaseModel):
    """Simple success body."""

    ok: bool = True


class MeResponse(BaseModel):
    """GET /me."""

    email: str
    role: str
    employee_id: int | None
    must_change_password: bool
    company_name: str
