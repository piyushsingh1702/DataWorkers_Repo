"""Profiling endpoints."""

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.profiling_agent import run_profiling
from app.api.routes._common import DBNameRequest
from app.models.glossary import DataGlossary
from app.utils.db_registry import load_artifact, save_artifact

router = APIRouter(prefix="/api/v1/profiling", tags=["Profiling"])


class ProfilingEntryOverride(BaseModel):
    """Editable LLM-generated fields on a glossary entry."""

    business_description: str | None = None
    data_domain: str | None = None
    is_enumeration: bool | None = None
    enum_values: list[str] | None = None
    is_pii: bool | None = None


class ProfilingOverrideRequest(DBNameRequest):
    table_name: str = Field(..., description="Target table.")
    column_name: str | None = Field(
        default=None,
        description=(
            "Target column. If omitted, the override is applied to every "
            "glossary entry belonging to ``table_name``."
        ),
    )
    updates: dict = Field(
        ...,
        description=(
            "Fields to overwrite. Allowed keys: business_description, "
            "data_domain, is_enumeration, enum_values, is_pii."
        ),
    )


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


@router.post("/override")
def override_profiling_results(request: ProfilingOverrideRequest):
    """Manually overwrite LLM-generated profiling output for a table or column.

    If ``column_name`` is supplied, only that glossary entry is updated.
    Otherwise the override is applied to every entry belonging to
    ``table_name``.
    """
    payload = load_artifact(request.db_name, "data_glossary")
    if not payload:
        raise HTTPException(status_code=404, detail="Data glossary not found. Run profiling first.")

    glossary = DataGlossary.model_validate_json(payload)

    if request.column_name is None:
        targets = [e for e in glossary.entries if e.table_name == request.table_name]
    else:
        targets = [
            e
            for e in glossary.entries
            if e.table_name == request.table_name and e.column_name == request.column_name
        ]

    if not targets:
        scope = (
            f"table '{request.table_name}'"
            if request.column_name is None
            else f"column '{request.table_name}.{request.column_name}'"
        )
        raise HTTPException(status_code=404, detail=f"No glossary entries found for {scope}.")

    try:
        validated = ProfilingEntryOverride.model_validate(request.updates)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid updates: {e}")

    update_fields = validated.model_dump(exclude_unset=True)
    for entry in targets:
        for field, value in update_fields.items():
            setattr(entry, field, value)

    save_artifact(request.db_name, "data_glossary", glossary.model_dump_json())

    return {
        "status": "success",
        "db_name": request.db_name,
        "message": f"Overrode profiling output for {len(targets)} entr{'y' if len(targets) == 1 else 'ies'}",
        "updated_entries": [
            {"table": e.table_name, "column": e.column_name} for e in targets
        ],
        "applied_updates": update_fields,
    }
