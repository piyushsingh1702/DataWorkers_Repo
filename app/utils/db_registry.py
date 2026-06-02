"""Central registry for SQLite databases managed by the platform.

The registry lives in a dedicated SQLite database (``dq_admin.db``) under
``settings.database_dir``. It contains the ``dq_admin_databases`` table which
acts as the master directory of every named database the user has created via
``POST /api/v1/database/setup``.

All other API endpoints accept a ``db_name`` and resolve it to a file path via
``resolve_db_path``. This module is also the source of truth for the dynamic
``db_name`` dropdown rendered in the OpenAPI/Swagger UI.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.config.settings import settings

_REGISTRY_FILENAME = "dq_admin.db"

# Artifact kinds persisted as JSON blobs in dedicated tables. New runs overwrite
# the previous artifact for the same (db_name) via UPSERT.
ARTIFACT_KINDS = (
    "technical_catalogue",
    "data_glossary",
    "classification_report",
    "dq_rules",
    "dq_scores",
)

_REGISTRY_DDL = """
CREATE TABLE IF NOT EXISTS dq_admin_databases (
    db_name TEXT PRIMARY KEY,
    db_path TEXT NOT NULL UNIQUE,
    description TEXT,
    properties_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dq_admin_artifacts (
    db_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (db_name, kind)
);

CREATE TABLE IF NOT EXISTS dq_admin_dq_report (
    db_name TEXT PRIMARY KEY,
    markdown TEXT NOT NULL,
    generated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def registry_path() -> Path:
    """Return the path to the central registry database, creating its parent dir."""
    base = Path(settings.database_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base / _REGISTRY_FILENAME


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(registry_path()))
    conn.executescript(_REGISTRY_DDL)
    return conn


def register_database(
    db_name: str,
    db_path: str,
    description: str | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    """Insert or update a database entry in the central registry."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO dq_admin_databases (db_name, db_path, description, properties_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(db_name) DO UPDATE SET
                db_path = excluded.db_path,
                description = excluded.description,
                properties_json = excluded.properties_json,
                updated_at = datetime('now')
            """,
            (db_name, db_path, description, json.dumps(properties) if properties else None),
        )
        conn.commit()


def list_databases() -> list[dict[str, Any]]:
    """Return all registered databases as dictionaries."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT db_name, db_path, description, properties_json, created_at, updated_at
            FROM dq_admin_databases
            ORDER BY db_name
            """
        ).fetchall()
    return [
        {
            "db_name": r[0],
            "db_path": r[1],
            "description": r[2],
            "properties": json.loads(r[3]) if r[3] else None,
            "created_at": r[4],
            "updated_at": r[5],
        }
        for r in rows
    ]


def list_database_names() -> list[str]:
    """Return just the registered db_name values, sorted."""
    with _connect() as conn:
        return [
            r[0]
            for r in conn.execute(
                "SELECT db_name FROM dq_admin_databases ORDER BY db_name"
            ).fetchall()
        ]


def resolve_db_path(db_name: str | None) -> str:
    """Resolve a db_name to its file path via the registry.

    If ``db_name`` is None, falls back to ``settings.default_db_name``. Raises
    ``LookupError`` if the name is not registered.
    """
    name = db_name or settings.default_db_name
    with _connect() as conn:
        row = conn.execute(
            "SELECT db_path FROM dq_admin_databases WHERE db_name = ?",
            (name,),
        ).fetchone()
    if not row:
        raise LookupError(
            f"Database '{name}' is not registered. "
            "Create it via POST /api/v1/database/setup first."
        )
    return row[0]


def _resolve_name(db_name: str | None) -> str:
    return db_name or settings.default_db_name


def save_artifact(db_name: str | None, kind: str, payload_json: str) -> None:
    """Persist (overwrite) a JSON artifact for a database in dq_admin.

    Args:
        db_name: Registered database name (defaults to ``settings.default_db_name``).
        kind: One of :data:`ARTIFACT_KINDS`.
        payload_json: Already-serialized JSON string (e.g. ``model.model_dump_json()``).
    """
    if kind not in ARTIFACT_KINDS:
        raise ValueError(f"Unknown artifact kind '{kind}'. Expected one of {ARTIFACT_KINDS}.")
    name = _resolve_name(db_name)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO dq_admin_artifacts (db_name, kind, payload_json, generated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(db_name, kind) DO UPDATE SET
                payload_json = excluded.payload_json,
                generated_at = excluded.generated_at
            """,
            (name, kind, payload_json),
        )
        conn.commit()


def load_artifact(db_name: str | None, kind: str) -> str | None:
    """Return the raw JSON string for an artifact, or None if missing."""
    if kind not in ARTIFACT_KINDS:
        raise ValueError(f"Unknown artifact kind '{kind}'. Expected one of {ARTIFACT_KINDS}.")
    name = _resolve_name(db_name)
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload_json FROM dq_admin_artifacts WHERE db_name = ? AND kind = ?",
            (name, kind),
        ).fetchone()
    return row[0] if row else None


def save_dq_report_markdown(db_name: str | None, markdown: str) -> None:
    """Persist (overwrite) the DQ markdown report for a database."""
    name = _resolve_name(db_name)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO dq_admin_dq_report (db_name, markdown, generated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(db_name) DO UPDATE SET
                markdown = excluded.markdown,
                generated_at = excluded.generated_at
            """,
            (name, markdown),
        )
        conn.commit()


def load_dq_report_markdown(db_name: str | None) -> str | None:
    name = _resolve_name(db_name)
    with _connect() as conn:
        row = conn.execute(
            "SELECT markdown FROM dq_admin_dq_report WHERE db_name = ?",
            (name,),
        ).fetchone()
    return row[0] if row else None
