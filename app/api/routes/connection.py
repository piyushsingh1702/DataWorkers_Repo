"""Connection test endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents.connection_agent import run_connection_test

router = APIRouter(prefix="/api/v1/connection", tags=["Connection"])


class ConnectionRequest(BaseModel):
    db_path: str | None = None


@router.post("/test")
def test_connection(request: ConnectionRequest = ConnectionRequest()):
    """Test database connectivity."""
    result = run_connection_test(request.db_path)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result
