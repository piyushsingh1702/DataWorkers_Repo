"""Discovery endpoints."""

from fastapi import APIRouter, HTTPException

from app.agents.discovery_agent import run_discovery
from app.config.settings import settings

router = APIRouter(prefix="/api/v1/discovery", tags=["Discovery"])


@router.post("/run")
def run_discovery_agent():
    """Run the discovery agent to build a technical catalogue."""
    try:
        catalogue = run_discovery()
        return {
            "status": "success",
            "message": f"Discovered {catalogue.total_tables} tables, {catalogue.total_columns} columns",
            "summary": {
                "total_tables": catalogue.total_tables,
                "total_columns": catalogue.total_columns,
                "tables": [t.name for t in catalogue.tables],
            },
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
def get_discovery_results():
    """Get the technical catalogue results."""
    output_path = settings.outputs_path / "technical_catalogue.json"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="Technical catalogue not found. Run discovery first.")
    import json
    return json.loads(output_path.read_text())
