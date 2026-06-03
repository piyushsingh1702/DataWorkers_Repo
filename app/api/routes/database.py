"""Database setup endpoints."""

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app.database.setup_mortgage_sample_db import create_mortgage_database
from app.utils.db_registry import list_databases, list_snapshots_for, list_snapshot_dates

router = APIRouter(prefix="/api/v1/database", tags=["Database"])

_SNAPSHOT_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DatabaseSetupRequest(BaseModel):
    db_name: str | None = Field(
        default=None,
        description="Unique database name (used as the SQLite filename).",
    )
    snapshot_date: str = Field(
        ...,
        description=(
            "Snapshot date for the data being loaded, in ISO format YYYY-MM-DD "
            "(e.g. '2025-01-01'). Every row inserted by this call is tagged "
            "with this date in the `report_date` column. Re-call this endpoint "
            "with a different snapshot_date to append more snapshots to the "
            "same tables."
        ),
        examples=["2025-01-01"],
    )
    description: str | None = Field(
        default=None,
        description="Optional description stored in the dq_admin schema.",
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata dict stored as JSON in the dq_admin schema.",
    )

    @field_validator("snapshot_date")
    @classmethod
    def _validate_snapshot_date(cls, v: str) -> str:
        if not isinstance(v, str) or not _SNAPSHOT_DATE_PATTERN.match(v):
            raise ValueError(
                "snapshot_date must be ISO format YYYY-MM-DD (e.g. '2025-01-01')."
            )
        from datetime import datetime as _dt
        try:
            _dt.strptime(v, "%Y-%m-%d")
        except ValueError as e:
            raise ValueError(f"snapshot_date '{v}' is not a real calendar date: {e}")
        return v


@router.post("/setup")
def setup_database(payload: DatabaseSetupRequest):
    """Load one data snapshot into a sample SQLite database.

    Behavior is implicit:

    * **New ``snapshot_date`` for an existing database** → rows are appended;
      previous snapshots are preserved.
    * **Same ``(db_name, snapshot_date)`` as a previous call** → only that
      snapshot's rows (and its dq_admin artifacts / DQ report) are replaced.
      Other snapshots in the same database are left intact.
    * **First call for a ``db_name``** → the SQLite file and schema are
      created automatically.
    """
    try:
        db_path = create_mortgage_database(
            db_name=payload.db_name,
            snapshot_date=payload.snapshot_date,
            description=payload.description,
            properties=payload.properties,
        )
        return {
            "status": "success",
            "message": f"Snapshot '{payload.snapshot_date}' loaded.",
            "db_name": payload.db_name,
            "snapshot_date": payload.snapshot_date,
            "path": db_path,
            "snapshots": list_snapshots_for(payload.db_name) if payload.db_name else [],
        }
    except (ValueError, FileExistsError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
def list_registered_databases():
    """List all databases registered in the central dq_admin registry."""
    return {"databases": list_databases()}


@router.get("/snapshots")
def list_snapshots(db_name: str | None = Query(default=None)):
    """List snapshot dates registered for a database (or all databases when ``db_name`` is omitted)."""
    if db_name:
        return {"db_name": db_name, "snapshots": list_snapshots_for(db_name)}
    return {"snapshots": list_snapshot_dates()}

