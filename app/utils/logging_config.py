"""Centralized logging configuration.

Writes rotating log files under ``settings.log_dir`` (default ``app/logs/``):

- ``app.log``    — every log record from the application (INFO+ by default).
- ``api_access.log`` — one line per HTTP request handled by the API
                        (method, path, query, status, duration, client).
- ``agents/<agent>.log`` — one file per agent module (e.g. ``discovery_agent.log``)
                        capturing only that agent's records. Records still
                        propagate to ``app.log`` for a unified view.

A console handler is also attached for local dev visibility.
"""

from __future__ import annotations

import logging
import time
from logging.handlers import RotatingFileHandler

from fastapi import FastAPI, Request

from app.config.settings import settings

_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_ACCESS_FORMAT = "%(asctime)s %(message)s"

# Dedicated logger for HTTP request access logs. Kept separate so it can be
# routed to its own file without polluting app.log.
access_logger = logging.getLogger("app.access")
access_logger.setLevel(logging.INFO)
access_logger.propagate = False  # don't bubble up into root/app.log


# Agent modules under app.agents.* that should each get their own log file.
_AGENT_MODULES = (
    "classification_agent",
    "connection_agent",
    "discovery_agent",
    "dq_executor_agent",
    "dq_rules_agent",
    "orchestrator",
    "profiling_agent",
    "qa_agent",
)


def _configure_agent_loggers(log_dir) -> None:
    """Attach a dedicated rotating file handler to each agent logger."""
    agents_dir = log_dir / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    for module in _AGENT_MODULES:
        agent_logger = logging.getLogger(f"app.agents.{module}")
        agent_logger.setLevel(level)
        # Records still propagate so app.log captures everything as well.
        already = any(
            isinstance(h, RotatingFileHandler) and getattr(h, "_agent_log", None) == module
            for h in agent_logger.handlers
        )
        if already:
            continue
        handler = RotatingFileHandler(
            agents_dir / f"{module}.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter(_FORMAT))
        handler._agent_log = module  # type: ignore[attr-defined]
        agent_logger.addHandler(handler)


def configure_logging() -> None:
    """Configure root + access loggers with rotating file handlers.

    Idempotent — safe to call multiple times (existing handlers are not
    duplicated).
    """
    log_dir = settings.logs_path  # creates app/logs/ if missing
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    has_app_file = any(
        isinstance(h, RotatingFileHandler) and getattr(h, "_app_log", False)
        for h in root.handlers
    )
    if not has_app_file:
        app_handler = RotatingFileHandler(
            log_dir / "app.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        app_handler.setFormatter(logging.Formatter(_FORMAT))
        app_handler._app_log = True  # type: ignore[attr-defined]
        root.addHandler(app_handler)

    has_console = any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, RotatingFileHandler)
        for h in root.handlers
    )
    if not has_console:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(_FORMAT))
        root.addHandler(console)

    has_access_file = any(
        isinstance(h, RotatingFileHandler) and getattr(h, "_access_log", False)
        for h in access_logger.handlers
    )
    if not has_access_file:
        access_handler = RotatingFileHandler(
            log_dir / "api_access.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        access_handler.setFormatter(logging.Formatter(_ACCESS_FORMAT))
        access_handler._access_log = True  # type: ignore[attr-defined]
        access_logger.addHandler(access_handler)

    _configure_agent_loggers(log_dir)


def install_request_logging(app: FastAPI) -> None:
    """Attach a middleware that logs every API request to ``api_access.log``."""

    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        start = time.perf_counter()
        client_host = request.client.host if request.client else "-"
        query = request.url.query
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            access_logger.exception(
                "%s %s%s status=500 duration_ms=%.1f client=%s",
                request.method,
                request.url.path,
                f"?{query}" if query else "",
                duration_ms,
                client_host,
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        access_logger.info(
            "%s %s%s status=%s duration_ms=%.1f client=%s",
            request.method,
            request.url.path,
            f"?{query}" if query else "",
            response.status_code,
            duration_ms,
            client_host,
        )
        return response
