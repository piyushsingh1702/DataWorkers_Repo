"""Classification endpoints."""

import json

from fastapi import APIRouter, HTTPException, Query

from app.agents.classification_agent import run_classification
from app.utils.db_registry import load_artifact

router = APIRouter(prefix="/api/v1/classification", tags=["Classification"])


@router.post("/run")
def run_classification_agent(db_name: str | None = Query(default=None)):
    """Run the classification agent to classify data and identify CDEs."""
    try:
        report = run_classification(db_name=db_name)
        return {
            "status": "success",
            "db_name": db_name,
            "message": f"Classified {report.total_columns} columns, identified {report.cde_count} CDEs",
            "summary": {
                "total_columns": report.total_columns,
                "cde_count": report.cde_count,
                "cde_percentage": report.cde_percentage,
                "classification_summary": report.classification_summary,
            },
        }
    except (FileNotFoundError, LookupError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
def get_classification_results(db_name: str | None = Query(default=None)):
    """Get the classification report results for a database."""
    payload = load_artifact(db_name, "classification_report")
    if not payload:
        raise HTTPException(status_code=404, detail="Classification report not found. Run classification first.")
    return json.loads(payload)
