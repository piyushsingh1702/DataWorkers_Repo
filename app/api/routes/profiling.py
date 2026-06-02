"""Profiling endpoints."""

import json

from fastapi import APIRouter, HTTPException, Query

from app.agents.profiling_agent import run_profiling
from app.utils.db_registry import load_artifact

router = APIRouter(prefix="/api/v1/profiling", tags=["Profiling"])


@router.post("/run")
def run_profiling_agent(db_name: str | None = Query(default=None)):
    """Run the profiling agent to generate data glossary."""
    try:
        glossary = run_profiling(db_name)
        return {
            "status": "success",
            "db_name": db_name,
            "message": f"Profiled {glossary.total_entries} columns",
            "summary": {
                "total_entries": glossary.total_entries,
                "pii_columns": sum(1 for e in glossary.entries if e.is_pii),
                "enumeration_columns": sum(1 for e in glossary.entries if e.is_enumeration),
            },
        }
    except (FileNotFoundError, LookupError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
def get_profiling_results(db_name: str | None = Query(default=None)):
    """Get the data glossary results for a database."""
    payload = load_artifact(db_name, "data_glossary")
    if not payload:
        raise HTTPException(status_code=404, detail="Data glossary not found. Run profiling first.")
    return json.loads(payload)
