"""Pipeline endpoints - run full pipeline or check status."""

from fastapi import APIRouter, HTTPException

from app.agents.orchestrator import get_pipeline_status, run_full_pipeline

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline"])


@router.post("/run")
def run_pipeline():
    """Run the full data quality pipeline (all steps sequentially)."""
    try:
        result = run_full_pipeline()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def pipeline_status():
    """Get the current pipeline execution status."""
    return get_pipeline_status()
