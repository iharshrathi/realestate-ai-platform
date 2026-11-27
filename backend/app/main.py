"""FastAPI application factory."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, request_id_ctx
from app.core.rate_limit import client_ip, limiter
from app.db.init_db import init_db
from app.db.session import SessionLocal, engine

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        init_db()
        if settings.auto_seed:
            from app.db.seed import seed_if_empty

            with SessionLocal() as db:
                seed_if_empty(db)
        logger.info("%s started (%s)", settings.app_name, settings.environment)
        yield

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description=(
            "AI-powered real-estate lead management: lead scoring (ML), requirement extraction "
            "(NLP), follow-up assistant, RAG chatbot, LangGraph agents and sales analytics. "
            "Demo data is synthetic."
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_ctx.set(request_id)
        try:
            if request.url.path.startswith(settings.api_prefix) and not limiter.allow(
                f"global:{client_ip(request)}", settings.rate_limit_global_per_minute
            ):
                return JSONResponse(
                    status_code=429, content={"detail": "Too many requests. Please slow down."}
                )
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response
        finally:
            request_id_ctx.reset(token)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Liveness probe plus a database connectivity check."""
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


app = create_app()
