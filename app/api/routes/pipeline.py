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
    extras: PipelineExtras | None = None,
):
    """Run the full data quality pipeline against a named database."""
    extras = extras or PipelineExtras()
    try:
        return run_full_pipeline(
            db_name=db_name,
            description=extras.description,
            properties=extras.properties,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def pipeline_status():
    """Get the current pipeline execution status."""
    return get_pipeline_status()
