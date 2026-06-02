"""Discovery endpoints."""

import json

from fastapi import APIRouter, HTTPException, Query

from app.agents.discovery_agent import run_discovery
from app.utils.db_registry import load_artifact

router = APIRouter(prefix="/api/v1/discovery", tags=["Discovery"])


@router.post("/run")
def run_discovery_agent(db_name: str | None = Query(default=None)):
    """Run the discovery agent to build a technical catalogue."""
    try:
        catalogue = run_discovery(db_name)
        return {
            "status": "success",
            "db_name": db_name,
            "message": f"Discovered {catalogue.total_tables} tables, {catalogue.total_columns} columns",
            "summary": {
                "total_tables": catalogue.total_tables,
                "total_columns": catalogue.total_columns,
                "tables": [t.name for t in catalogue.tables],
            },
        }
    except (FileNotFoundError, LookupError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
def get_discovery_results(db_name: str | None = Query(default=None)):
    """Get the technical catalogue results for a database."""
    payload = load_artifact(db_name, "technical_catalogue")
    if not payload:
        raise HTTPException(status_code=404, detail="Technical catalogue not found. Run discovery first.")
    return json.loads(payload)
