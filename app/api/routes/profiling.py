"""Profiling endpoints."""

import json

from fastapi import APIRouter, HTTPException

from app.agents.profiling_agent import run_profiling
from app.config.settings import settings

router = APIRouter(prefix="/api/v1/profiling", tags=["Profiling"])


@router.post("/run")
def run_profiling_agent():
    """Run the profiling agent to generate data glossary."""
    try:
        glossary = run_profiling()
        return {
            "status": "success",
            "message": f"Profiled {glossary.total_entries} columns",
            "summary": {
                "total_entries": glossary.total_entries,
                "pii_columns": sum(1 for e in glossary.entries if e.is_pii),
                "enumeration_columns": sum(1 for e in glossary.entries if e.is_enumeration),
            },
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
def get_profiling_results():
    """Get the data glossary results."""
    output_path = settings.outputs_path / "data_glossary.json"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Data glossary not found. Run profiling first.")
    return json.loads(output_path.read_text())
