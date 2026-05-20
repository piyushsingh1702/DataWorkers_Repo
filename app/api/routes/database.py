"""Database setup endpoints."""

from fastapi import APIRouter, HTTPException

from app.database.setup_sample_db import create_sample_database

router = APIRouter(prefix="/api/v1/database", tags=["Database"])


@router.post("/setup")
def setup_database():
    """Create or reset the sample SQLite database."""
    try:
        db_path = create_sample_database()
        return {"status": "success", "message": "Sample database created", "path": db_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
