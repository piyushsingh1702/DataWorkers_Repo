"""Database setup endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database.setup_sample_db import create_sample_database
from app.utils.db_registry import list_databases

router = APIRouter(prefix="/api/v1/database", tags=["Database"])


class DatabaseSetupRequest(BaseModel):
    db_name: str | None = Field(
        default=None,
        description="Unique database name (used as the SQLite filename).",
    )
    description: str | None = Field(
        default=None,
        description="Optional description stored in the dq_admin schema.",
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata dict stored as JSON in the dq_admin schema.",
    )
    overwrite: bool = Field(
        default=True,
        description="If true, overwrite an existing database with the same name.",
    )


@router.post("/setup")
def setup_database(payload: DatabaseSetupRequest | None = None):
    """Create or reset a sample SQLite database registered under the dq_admin schema."""
    payload = payload or DatabaseSetupRequest()
    try:
        db_path = create_sample_database(
            db_name=payload.db_name,
            description=payload.description,
            properties=payload.properties,
            overwrite=payload.overwrite,
        )
        return {
            "status": "success",
            "message": "Sample database created",
            "db_name": payload.db_name,
            "path": db_path,
        }
    except (ValueError, FileExistsError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
def list_registered_databases():
    """List all databases registered in the central dq_admin registry.

    The ``db_name`` values returned here populate the dropdown for every other
    endpoint that takes a ``db_name`` parameter.
    """
    return {"databases": list_databases()}

