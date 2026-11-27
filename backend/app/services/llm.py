"""Thin, optional LLM wrapper.

The platform works without any LLM: every LLM call site has a deterministic fallback, and the
API reports which path produced a result (``mode`` / ``generated_by``). When an LLM is enabled
its output is always validated before use (JSON schema, grounding checks).
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any, Protocol

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    def complete(self, *, system: str, prompt: str, max_tokens: int | None = None) -> str: ...


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, timeout: float, max_tokens: int) -> None:
        import anthropic  # imported lazily so the SDK is only needed when the LLM is enabled

        self._client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=1)
        self._model = model
        self._max_tokens = max_tokens

    def complete(self, *, system: str, prompt: str, max_tokens: int | None = None) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens or self._max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in response.content if block.type == "text").strip()


@lru_cache
def get_llm() -> LLMClient | None:
    """Return the configured LLM client, or ``None`` when no LLM is enabled."""
    settings = get_settings()
    if not settings.llm_enabled or settings.anthropic_api_key is None:
        return None
    return AnthropicLLM(
        api_key=settings.anthropic_api_key.get_secret_value(),
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
        max_tokens=settings.llm_max_tokens,
    )


def safe_complete(*, system: str, prompt: str, max_tokens: int | None = None) -> str | None:
    """Call the LLM, returning ``None`` on any failure (callers then use their fallback)."""
    client = get_llm()
    if client is None:
        return None
    try:
        text = client.complete(system=system, prompt=prompt, max_tokens=max_tokens)
        return text or None
    except Exception:  # network errors, rate limits, auth errors, SDK changes...
        logger.warning("LLM call failed; using deterministic fallback", exc_info=True)
        return None


_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from an LLM reply (models sometimes add prose/fences)."""
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
