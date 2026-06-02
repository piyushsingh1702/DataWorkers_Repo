"""Connection test endpoints."""

from fastapi import APIRouter, HTTPException, Query

from app.agents.connection_agent import run_connection_test

router = APIRouter(prefix="/api/v1/connection", tags=["Connection"])


@router.post("/test")
def test_connection(db_name: str | None = Query(default=None)):
    """Test connectivity to a registered database."""
    try:
        result = run_connection_test(db_name)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result
