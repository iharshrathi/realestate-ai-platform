"""Collects every router under the versioned API prefix."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routers import ai, analytics, auth, campaigns, follow_ups, leads, properties, users

api_router = APIRouter()
for module in (auth, users, leads, follow_ups, properties, campaigns, analytics, ai):
    api_router.include_router(module.router)
