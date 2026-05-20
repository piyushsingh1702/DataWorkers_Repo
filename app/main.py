"""FastAPI application entry point for the Data Quality Research Assistant."""

import logging

from fastapi import FastAPI

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
