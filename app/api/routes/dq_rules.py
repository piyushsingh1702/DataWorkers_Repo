"""DQ Rules endpoints."""

import json

from fastapi import APIRouter, HTTPException

from app.agents.dq_rules_agent import run_dq_rules_generation
from app.config.settings import settings

router = APIRouter(prefix="/api/v1/dq-rules", tags=["DQ Rules"])


@router.post("/generate")
def generate_dq_rules():
    """Generate data quality rules using AI."""
    try:
        rule_set = run_dq_rules_generation()
        return {
            "status": "success",
            "message": f"Generated {rule_set.total_rules} DQ rules",
            "summary": {
                "total_rules": rule_set.total_rules,
                "rules_by_dimension": rule_set.rules_by_dimension,
                "rules_by_type": rule_set.rules_by_type,
            },
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
def get_dq_rules():
    """Get the generated DQ rules."""
    output_path = settings.outputs_path / "dq_rules.json"
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="DQ rules not found. Run rule generation first.")
    return json.loads(output_path.read_text())


@router.post("/execute")
def execute_dq_rules():
    """Execute DQ rules and produce scores."""
    from app.agents.dq_executor_agent import run_dq_execution
    try:
        report = run_dq_execution()
        return {
            "status": "success",
            "message": f"Executed {report.total_rules} rules. Overall score: {report.overall_score}%",
            "summary": {
                "overall_score": report.overall_score,
                "total_rules": report.total_rules,
                "rules_passed": report.rules_passed,
                "rules_failed": report.rules_failed,
            },
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
