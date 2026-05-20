"""DQ Scores endpoints."""

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from app.config.settings import settings

router = APIRouter(prefix="/api/v1/dq-scores", tags=["DQ Scores"])


@router.get("/results")
def get_dq_scores():
    """Get the DQ execution scores (JSON)."""
    output_path = settings.outputs_path / "dq_scores.json"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="DQ scores not found. Execute DQ rules first.")
    return json.loads(output_path.read_text())


@router.get("/report", response_class=PlainTextResponse)
def get_dq_report():
    """Get the DQ report as markdown."""
    output_path = settings.outputs_path / "dq_report.md"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="DQ report not found. Execute DQ rules first.")
    return output_path.read_text()
