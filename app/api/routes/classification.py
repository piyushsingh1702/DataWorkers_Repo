"""Classification endpoints."""

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.classification_agent import run_classification
from app.api.routes._common import DBNameRequest
from app.models.classification import ClassificationReport
from app.utils.db_registry import load_artifact, save_artifact

router = APIRouter(prefix="/api/v1/classification", tags=["Classification"])


class ClassificationOverride(BaseModel):
    """Editable LLM-generated fields on a column classification."""

    classification: str | None = Field(
        default=None,
        description="One of: Public, Internal, Confidential, Restricted.",
    )
    is_cde: bool | None = Field(default=None, description="Critical Data Element flag.")
    cde_rationale: str | None = None
    classification_rationale: str | None = None


class ClassificationOverrideRequest(DBNameRequest):
    table_name: str = Field(..., description="Target table.")
    column_name: str | None = Field(
        default=None,
        description=(
            "Target column. If omitted, the override is applied to every "
            "classification entry belonging to ``table_name``."
        ),
    )
    updates: dict = Field(
        ...,
        description=(
            "Fields to overwrite. Allowed keys: classification, is_cde, "
            "cde_rationale, classification_rationale."
        ),
    )


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


_ALLOWED_CLASSIFICATIONS = {"Public", "Internal", "Confidential", "Restricted"}


@router.post("/override")
def override_classification_results(request: ClassificationOverrideRequest):
    """Manually overwrite LLM-generated classification, CDE flag, and reasonings.

    If ``column_name`` is supplied, only that classification entry is updated.
    Otherwise the override is applied to every entry belonging to
    ``table_name``. Classification summary counters are recomputed after the
    edit so aggregate stats stay consistent.
    """
    payload = load_artifact(request.db_name, "classification_report")
    if not payload:
        raise HTTPException(status_code=404, detail="Classification report not found. Run classification first.")

    report = ClassificationReport.model_validate_json(payload)

    if request.column_name is None:
        targets = [c for c in report.classifications if c.table_name == request.table_name]
    else:
        targets = [
            c
            for c in report.classifications
            if c.table_name == request.table_name and c.column_name == request.column_name
        ]

    if not targets:
        scope = (
            f"table '{request.table_name}'"
            if request.column_name is None
            else f"column '{request.table_name}.{request.column_name}'"
        )
        raise HTTPException(status_code=404, detail=f"No classification entries found for {scope}.")

    try:
        validated = ClassificationOverride.model_validate(request.updates)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid updates: {e}")

    update_fields = validated.model_dump(exclude_unset=True)
    if "classification" in update_fields and update_fields["classification"] not in _ALLOWED_CLASSIFICATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"classification must be one of {sorted(_ALLOWED_CLASSIFICATIONS)}.",
        )

    for entry in targets:
        for field, value in update_fields.items():
            setattr(entry, field, value)

    # Recompute aggregate stats so the report stays internally consistent.
    summary: dict[str, int] = {}
    for c in report.classifications:
        summary[c.classification] = summary.get(c.classification, 0) + 1
    report.classification_summary = summary
    report.cde_count = sum(1 for c in report.classifications if c.is_cde)
    report.cde_percentage = (
        round((report.cde_count / report.total_columns) * 100, 2)
        if report.total_columns
        else 0.0
    )

    save_artifact(request.db_name, "classification_report", report.model_dump_json())

    return {
        "status": "success",
        "db_name": request.db_name,
        "message": f"Overrode classification output for {len(targets)} entr{'y' if len(targets) == 1 else 'ies'}",
        "updated_entries": [
            {"table": c.table_name, "column": c.column_name} for c in targets
        ],
        "applied_updates": update_fields,
        "summary": {
            "classification_summary": report.classification_summary,
            "cde_count": report.cde_count,
            "cde_percentage": report.cde_percentage,
        },
    }
