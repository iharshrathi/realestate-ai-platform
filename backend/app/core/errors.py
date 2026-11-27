"""Domain exceptions and their HTTP mapping.

Services raise these; one exception handler turns them into JSON responses. That keeps
HTTP concerns out of the service layer.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.logging import request_id_ctx

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    default_detail = "Bad request"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class NotFoundError(AppError):
    status_code = 404
    default_detail = "Resource not found"


class ForbiddenError(AppError):
    status_code = 403
    default_detail = "You do not have permission to do that"


class ConflictError(AppError):
    status_code = 409
    default_detail = "Conflict with the current state of the resource"


class ServiceUnavailableError(AppError):
    status_code = 503
    default_detail = "Service temporarily unavailable"


class ModelNotAvailableError(ServiceUnavailableError):
    default_detail = "The lead-scoring model is not available. Train it with `make train`."


def _json_error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"detail": detail, "request_id": request_id_ctx.get()}
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        return _json_error(exc.status_code, exc.detail)

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Integrity error: %s", exc.orig)
        return _json_error(409, "The change conflicts with existing data")

    @app.exception_handler(Exception)
    async def handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Log the traceback server-side; never leak internals to the client.
        logger.exception("Unhandled error", exc_info=exc)
        return _json_error(500, "Internal server error")
