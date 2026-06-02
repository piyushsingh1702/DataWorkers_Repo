"""FastAPI application entry point for the Data Quality Research Assistant."""

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from app.api.routes import (
    database,
    connection,
    discovery,
    profiling,
    classification,
    dq_rules,
    dq_scores,
    pipeline,
)
from app.config.settings import settings
from app.utils.db_registry import list_database_names

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = FastAPI(
    title="Metadata & Data Insights Research Assistant",
    description=(
        "Autonomous agentic platform for data quality assessment. "
        "Performs discovery, profiling, classification, and data quality rule generation & execution."
    ),
    version="0.1.0",
)

# Register routes
app.include_router(database.router)
app.include_router(connection.router)
app.include_router(discovery.router)
app.include_router(profiling.router)
app.include_router(classification.router)
app.include_router(dq_rules.router)
app.include_router(dq_scores.router)
app.include_router(pipeline.router)


def _inject_db_name_enum(schema: dict[str, Any], db_names: list[str]) -> None:
    """Walk the OpenAPI schema and set ``enum`` on every ``db_name`` property/parameter.

    This turns the free-text ``db_name`` field into a dropdown in Swagger UI
    populated from the central dq_admin registry. The schema is regenerated on
    every request so newly created databases appear immediately.
    """
    if not db_names:
        return

    def _patch_property(prop: dict[str, Any]) -> None:
        # Drop ``anyOf`` (used for ``str | None``) so Swagger renders an enum dropdown.
        if "anyOf" in prop:
            prop.pop("anyOf", None)
            prop["type"] = "string"
        prop["enum"] = db_names

    # Patch request body schemas
    for component in schema.get("components", {}).get("schemas", {}).values():
        props = component.get("properties", {})
        if "db_name" in props:
            _patch_property(props["db_name"])

    # Patch query/path parameters named db_name
    for path_item in schema.get("paths", {}).values():
        for op in path_item.values():
            if not isinstance(op, dict):
                continue
            for param in op.get("parameters", []) or []:
                if param.get("name") == "db_name":
                    _patch_property(param.setdefault("schema", {}))


def _customize_openapi():
    """Build the OpenAPI schema fresh on every call so the db_name dropdown stays live."""
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    try:
        _inject_db_name_enum(schema, list_database_names())
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger(__name__).warning(
            "Failed to inject db_name enum into OpenAPI schema: %s", exc
        )
    # Do NOT cache: ensures dropdown reflects newly registered databases without restart.
    app.openapi_schema = None
    return schema


app.openapi = _customize_openapi


@app.get("/", tags=["Health"])
def root():
    """Health check endpoint."""
    return {
        "service": "Metadata & Data Insights Research Assistant",
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/api/v1/outputs", tags=["Outputs"])
def list_outputs():
    """List available output files."""
    outputs_dir = settings.outputs_path
    files = []
    if outputs_dir.exists():
        for f in outputs_dir.iterdir():
            if f.is_file():
                files.append({"name": f.name, "size_bytes": f.stat().st_size})
    return {"outputs": files}
