"""Structured logging of agent-to-agent interactions.

This module emits one log line per inter-agent event so the
``logs/agents/interactions.log`` file becomes a chronological transcript of
how information flows through the pipeline. Each line is a single JSON
object so it is grep-friendly *and* machine-parseable.

Event kinds:

- ``handoff``  — an agent finished and is passing an artifact to the next agent
- ``gate``     — the orchestrator's completeness check on the upstream artifact
- ``halt``     — the pipeline stopped because a gate failed
- ``request``  — an agent invoked a downstream service (LLM, DB, sibling)
- ``response`` — that downstream service answered

The intent is for evaluators / operators to be able to read the file
top-to-bottom and reconstruct the conversation between agents.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import settings

_LOGGER_NAME = "app.interactions"
_FORMAT = "%(asctime)s %(message)s"

interaction_logger = logging.getLogger(_LOGGER_NAME)
interaction_logger.setLevel(logging.INFO)
interaction_logger.propagate = False  # keep the transcript out of app.log


def _ensure_handler() -> None:
    if any(
        isinstance(h, logging.handlers.RotatingFileHandler)
        and getattr(h, "_interactions_log", False)
        for h in interaction_logger.handlers
    ):
        return
    log_dir: Path = settings.logs_path / "agents"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        log_dir / "interactions.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(_FORMAT))
    handler._interactions_log = True  # type: ignore[attr-defined]
    interaction_logger.addHandler(handler)


def _emit(event: str, **fields: Any) -> dict[str, Any]:
    """Write a single JSON event line to interactions.log and return it."""
    _ensure_handler()
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
    }
    payload.update({k: v for k, v in fields.items() if v is not None})
    try:
        line = json.dumps(payload, default=str, ensure_ascii=False)
    except Exception:
        line = json.dumps({"ts": payload["ts"], "event": event, "error": "serialize_failed"})
    interaction_logger.info(line)
    return payload


def log_handoff(
    sender: str,
    receiver: str,
    artifact: str,
    *,
    db_name: str | None = None,
    snapshot_date: str | None = None,
    summary: dict[str, Any] | None = None,
) -> None:
    """`sender` finished producing `artifact` and is passing it to `receiver`.

    `summary` should be a small dict of headline metrics (e.g. table count,
    rule count) so the interaction log is useful without opening artifacts.
    """
    _emit(
        "handoff",
        sender=sender,
        receiver=receiver,
        artifact=artifact,
        db_name=db_name,
        snapshot_date=snapshot_date,
        summary=summary,
    )


def log_gate(
    stage: str,
    *,
    score: float,
    threshold: float,
    passed: bool,
    issues: list[str] | None = None,
    warnings: list[str] | None = None,
    db_name: str | None = None,
    snapshot_date: str | None = None,
) -> None:
    """The orchestrator's completeness check on an upstream artifact."""
    _emit(
        "gate",
        stage=stage,
        score=score,
        threshold=threshold,
        passed=passed,
        issues=(issues or [])[:10],
        warnings=(warnings or [])[:10],
        db_name=db_name,
        snapshot_date=snapshot_date,
    )


def log_halt(
    *,
    blocked_at: str,
    reason: str,
    db_name: str | None = None,
    snapshot_date: str | None = None,
) -> None:
    """The pipeline stopped before the next agent ran."""
    _emit(
        "halt",
        blocked_at=blocked_at,
        reason=reason,
        db_name=db_name,
        snapshot_date=snapshot_date,
    )
