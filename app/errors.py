"""Custom errors and the ONE place that maps them to HTTP responses.

Every error the client sees has the same shape:
    {"error": {"code": "...", "message": "..."}}
Stack traces never reach the client.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("hcm")


class AppError(Exception):
    """Base class for all expected errors. Subclasses set status and code."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class AuthError(AppError):
    """401: bad or missing token, wrong credentials."""

    status_code = 401
    code = "unauthorized"


class ForbiddenError(AppError):
    """403: role not allowed, or not your own data."""

    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    """404: the thing does not exist."""

    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """409: duplicates, for example a second check-in or a second setup."""

    status_code = 409
    code = "conflict"


class RuleViolationError(AppError):
    """422: a business rule says no, for example overlapping leave."""

    status_code = 422
    code = "rule_violation"


def install_error_handlers(app: FastAPI) -> None:
    """Attach all error handlers to the app. Called once from main."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        message = f"Invalid request: {first.get('msg', 'bad input')}"
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "invalid_request", "message": message}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Log the real error server-side; the client only gets a friendly line.
        logger.exception("Unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong on our side. Please try again.",
                }
            },
        )
