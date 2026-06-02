"""Discovery endpoints."""

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.discovery_agent import run_discovery
from app.api.routes._common import DBNameRequest
from app.models.catalogue import TechnicalCatalogue
from app.utils.db_registry import load_artifact, save_artifact

router = APIRouter(prefix="/api/v1/discovery", tags=["Discovery"])


class DiscoveryTableOverride(BaseModel):
    """Editable fields on a table-level discovery entry."""

    description: str | None = Field(default=None, description="Business / technical description for the table.")


class DiscoveryColumnOverride(BaseModel):
    """Editable fields on a column-level discovery entry."""

    data_type: str | None = None
    nullable: bool | None = None
    default_value: str | None = None
    is_primary_key: bool | None = None
    is_unique: bool | None = None
    description: str | None = None


class DiscoveryOverrideRequest(DBNameRequest):
    table_name: str = Field(..., description="Target table to modify.")
    column_name: str | None = Field(
        default=None,
        description="Target column. If omitted, the override applies to the table itself.",
    )
    updates: dict = Field(
        ...,
        description=(
            "Fields to overwrite. Allowed keys for tables: description. "
            "Allowed keys for columns: data_type, nullable, default_value, "
            "is_primary_key, is_unique, description."
        ),
    )


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


@router.post("/override")
def override_discovery_results(request: DiscoveryOverrideRequest):
    """Manually overwrite LLM-generated discovery output for a table or column.

    Loads the persisted technical catalogue, applies the user's edits to the
    matching table (and optional column), revalidates the model, and saves it
    back. Existing fields not present in ``updates`` are preserved.
    """
    payload = load_artifact(request.db_name, "technical_catalogue")
    if not payload:
        raise HTTPException(status_code=404, detail="Technical catalogue not found. Run discovery first.")

    catalogue = TechnicalCatalogue.model_validate_json(payload)

    table = next((t for t in catalogue.tables if t.name == request.table_name), None)
    if table is None:
        raise HTTPException(status_code=404, detail=f"Table '{request.table_name}' not found in catalogue.")

    if request.column_name is None:
        # Table-level override
        try:
            validated = DiscoveryTableOverride.model_validate(request.updates)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid table updates: {e}")
        for field, value in validated.model_dump(exclude_unset=True).items():
            setattr(table, field, value)
        target = {"table": table.name}
    else:
        column = next((c for c in table.columns if c.name == request.column_name), None)
        if column is None:
            raise HTTPException(
                status_code=404,
                detail=f"Column '{request.column_name}' not found in table '{request.table_name}'.",
            )
        try:
            validated = DiscoveryColumnOverride.model_validate(request.updates)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid column updates: {e}")
        for field, value in validated.model_dump(exclude_unset=True).items():
            setattr(column, field, value)
        target = {"table": table.name, "column": column.name}

    save_artifact(request.db_name, "technical_catalogue", catalogue.model_dump_json())

    return {
        "status": "success",
        "db_name": request.db_name,
        "message": f"Overrode discovery output for {target}",
        "applied_updates": validated.model_dump(exclude_unset=True),
    }
