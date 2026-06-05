"""Pipeline endpoints - run full pipeline or check status."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.orchestrator import get_pipeline_status, run_full_pipeline

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline"])


class PipelineExtras(BaseModel):
    description: str | None = Field(
        default=None, description="Optional description stored in the dq_admin registry."
    )
    properties: dict[str, Any] | None = Field(
        default=None,
        description="Optional metadata stored as JSON in the dq_admin registry.",
    )


@router.post("/run")
def run_pipeline(
    db_name: str | None = Query(default=None),
    snapshot_date: str = Query(..., description="Snapshot date (YYYY-MM-DD)."),
    setup_database: bool = Query(
        default=False,
        description="If true, recreate the sample DB with all default snapshots before running. Defaults to false.",
    ),
    extras: PipelineExtras | None = None,
):
    """Run the full data quality pipeline for a (db_name, snapshot_date)."""
    extras = extras or PipelineExtras()
    try:
        return run_full_pipeline(
            db_name=db_name,
            snapshot_date=snapshot_date,
            description=extras.description,
            properties=extras.properties,
            setup_database=setup_database,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def pipeline_status():
    """Get the current pipeline execution status."""
    return get_pipeline_status()
