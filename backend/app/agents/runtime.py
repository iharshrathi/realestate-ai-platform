"""Shared plumbing for agent graphs: run context, audit logging and safe node execution."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import AgentLog, User
from app.models.enums import AgentRunStatus
from app.schemas.agent import AgentStep

logger = logging.getLogger(__name__)

NodeFn = Callable[[dict[str, Any]], dict[str, Any]]


def summarise(value: Any, limit: int = 400) -> Any:
    """Make a value small and JSON-safe for the audit log."""
    if isinstance(value, dict):
        return {str(k): summarise(v, limit) for k, v in list(value.items())[:25]}
    if isinstance(value, (list, tuple)):
        return [summarise(v, limit) for v in value[:10]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


@dataclass
class AgentContext:
    """Everything an agent run needs. One instance per run."""

    db: Session
    user: User
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    steps: list[AgentStep] = field(default_factory=list)

    def node(self, agent_name: str, action: str, fn: NodeFn, lead_id: int | None = None) -> NodeFn:
        """Wrap a graph node so it is timed, logged to ``agent_logs`` and can never crash the run.

        A failing node records an error in the state and the graph continues with whatever the
        other agents can still do (graceful degradation).
        """

        def wrapper(state: dict[str, Any]) -> dict[str, Any]:
            started = time.perf_counter()
            status, error = AgentRunStatus.SUCCESS, None
            try:
                update = fn(state)
            except Exception as exc:
                logger.exception("Agent %s failed during %s", agent_name, action)
                self.db.rollback()  # discard partial writes from the failed step
                status, error = AgentRunStatus.FAILED, f"{type(exc).__name__}: {exc}"
                update = {"errors": [f"{agent_name}: {error}"]}
            duration_ms = int((time.perf_counter() - started) * 1000)

            self.steps.append(
                AgentStep(
                    agent=agent_name,
                    action=action,
                    status=status,
                    duration_ms=duration_ms,
                    error=error,
                )
            )
            self.db.add(
                AgentLog(
                    run_id=self.run_id,
                    agent_name=agent_name,
                    action=action,
                    lead_id=lead_id if lead_id is not None else state.get("lead_id"),
                    triggered_by_id=self.user.id,
                    status=status,
                    input_summary=summarise({k: v for k, v in state.items() if k != "errors"}),
                    output_summary=summarise(update),
                    error=error,
                    duration_ms=duration_ms,
                )
            )
            self.db.commit()
            return update

        return wrapper
