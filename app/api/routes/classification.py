"""Classification endpoints."""

import json

from fastapi import APIRouter, HTTPException

from app.agents.classification_agent import run_classification
from app.config.settings import settings

router = APIRouter(prefix="/api/v1/classification", tags=["Classification"])


@router.post("/run")
def run_classification_agent():
    """Run the classification agent to classify data and identify CDEs."""
    try:
        report = run_classification()
        return {
            "status": "success",
            "message": f"Classified {report.total_columns} columns, identified {report.cde_count} CDEs",
            "summary": {
                "total_columns": report.total_columns,
                "cde_count": report.cde_count,
                "cde_percentage": report.cde_percentage,
                "classification_summary": report.classification_summary,
            },
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
def get_classification_results():
    """Get the classification report results."""
    output_path = settings.outputs_path / "classification_report.json"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Classification report not found. Run classification first.")
    return json.loads(output_path.read_text())
