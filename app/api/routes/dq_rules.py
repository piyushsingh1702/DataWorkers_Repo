"""DQ Rules endpoints."""

import json

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.dq_rules_agent import run_dq_rules_generation
from app.api.routes._common import DBNameRequest
from app.models.dq_rules import DQRule, DQRuleSet
from app.utils.db_registry import load_artifact, save_artifact

router = APIRouter(prefix="/api/v1/dq-rules", tags=["DQ Rules"])


_ALLOWED_DIMENSIONS = {
    "Accuracy",
    "Completeness",
    "Consistency",
    "Timeliness",
    "Validity",
    "Uniqueness",
}
_ALLOWED_RULE_TYPES = {"technical", "business"}
_ALLOWED_SEVERITIES = {"low", "medium", "high", "critical"}


class DQRuleUpsert(BaseModel):
    """Editable fields on a DQ rule. Required fields are validated when adding a new rule."""

    rule_id: str | None = None
    rule_name: str | None = None
    dimension: str | None = None
    table_name: str | None = None
    column_name: str | None = None
    rule_type: str | None = None
    description: str | None = None
    sql_query: str | None = None
    threshold: float | None = None
    severity: str | None = None
    cde_linked: bool | None = None


class DQRuleOverrideRequest(DBNameRequest):
    rule_id: str = Field(
        ...,
        description=(
            "Identifier of the rule to modify. If no rule with this id exists, "
            "set ``create_if_missing=true`` to add it as a new rule."
        ),
    )
    updates: DQRuleUpsert = Field(
        ...,
        description="Fields to overwrite (or full rule definition when adding).",
    )
    create_if_missing: bool = Field(
        default=False,
        description="When true and ``rule_id`` is not found, insert a new rule.",
    )


@router.post("/generate")
def generate_dq_rules(
    db_name: str | None = Query(default=None),
    snapshot_date: str = Query(..., description="Snapshot date (YYYY-MM-DD)."),
):
    """Generate data quality rules using AI for one snapshot."""
    try:
        rule_set = run_dq_rules_generation(db_name=db_name, snapshot_date=snapshot_date)
        return {
            "status": "success",
            "db_name": db_name,
            "snapshot_date": snapshot_date,
            "message": f"Generated {rule_set.total_rules} DQ rules",
            "summary": {
                "total_rules": rule_set.total_rules,
                "rules_by_dimension": rule_set.rules_by_dimension,
                "rules_by_type": rule_set.rules_by_type,
            },
        }
    except (FileNotFoundError, LookupError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/results")
def get_dq_rules(
    db_name: str | None = Query(default=None),
    snapshot_date: str = Query(..., description="Snapshot date (YYYY-MM-DD)."),
):
    """Get the generated DQ rules for a (db_name, snapshot_date)."""
    try:
        payload = load_artifact(db_name, snapshot_date, "dq_rules")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not payload:
        raise HTTPException(status_code=404, detail="DQ rules not found. Run rule generation first.")
    return json.loads(payload)


def _validate_enums(fields: dict) -> None:
    if "dimension" in fields and fields["dimension"] not in _ALLOWED_DIMENSIONS:
        raise HTTPException(status_code=400, detail=f"dimension must be one of {sorted(_ALLOWED_DIMENSIONS)}.")
    if "rule_type" in fields and fields["rule_type"] not in _ALLOWED_RULE_TYPES:
        raise HTTPException(status_code=400, detail=f"rule_type must be one of {sorted(_ALLOWED_RULE_TYPES)}.")
    if "severity" in fields and fields["severity"] not in _ALLOWED_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity must be one of {sorted(_ALLOWED_SEVERITIES)}.")


def _recompute_aggregates(rule_set: DQRuleSet) -> None:
    rule_set.total_rules = len(rule_set.rules)
    by_dim: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for r in rule_set.rules:
        by_dim[r.dimension] = by_dim.get(r.dimension, 0) + 1
        by_type[r.rule_type] = by_type.get(r.rule_type, 0) + 1
    rule_set.rules_by_dimension = by_dim
    rule_set.rules_by_type = by_type


@router.post("/override")
def override_dq_rule(request: DQRuleOverrideRequest):
    """Modify an existing DQ rule or add a new one.

    Behavior:
    - If a rule with ``rule_id`` exists, only the fields present in ``updates``
      are overwritten (other fields preserved).
    - If no rule with ``rule_id`` exists and ``create_if_missing=true``, a new
      rule is inserted. All required ``DQRule`` fields must be provided in
      ``updates`` (defaults apply for ``threshold``, ``severity``, ``cde_linked``).
    - Aggregate counts (``total_rules``, ``rules_by_dimension``, ``rules_by_type``)
      are recomputed after the change.
    """
    payload = load_artifact(request.db_name, request.snapshot_date, "dq_rules")
    if not payload:
        raise HTTPException(status_code=404, detail="DQ rules not found. Run rule generation first.")

    rule_set = DQRuleSet.model_validate_json(payload)
    update_fields = request.updates.model_dump(exclude_unset=True)

    # Reject attempts to silently change rule_id via the body; the URL-level
    # rule_id is authoritative.
    body_rule_id = update_fields.pop("rule_id", None)
    if body_rule_id is not None and body_rule_id != request.rule_id:
        raise HTTPException(
            status_code=400,
            detail="updates.rule_id must match the top-level rule_id (or be omitted).",
        )

    _validate_enums(update_fields)

    existing = next((r for r in rule_set.rules if r.rule_id == request.rule_id), None)

    if existing is not None:
        for field, value in update_fields.items():
            setattr(existing, field, value)
        action = "updated"
        affected_rule = existing
    else:
        if not request.create_if_missing:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Rule '{request.rule_id}' not found. Pass create_if_missing=true to add it."
                ),
            )
        # Build a new rule. Required fields without defaults must be present.
        new_rule_payload = {"rule_id": request.rule_id, **update_fields}
        try:
            new_rule = DQRule.model_validate(new_rule_payload)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot create rule '{request.rule_id}': {e}",
            )
        rule_set.rules.append(new_rule)
        action = "created"
        affected_rule = new_rule

    _recompute_aggregates(rule_set)
    save_artifact(request.db_name, request.snapshot_date, "dq_rules", rule_set.model_dump_json())

    return {
        "status": "success",
        "db_name": request.db_name,
        "snapshot_date": request.snapshot_date,
        "action": action,
        "message": f"Rule '{request.rule_id}' {action}.",
        "applied_updates": update_fields,
        "rule": affected_rule.model_dump(),
        "summary": {
            "total_rules": rule_set.total_rules,
            "rules_by_dimension": rule_set.rules_by_dimension,
            "rules_by_type": rule_set.rules_by_type,
        },
    }


@router.post("/execute")
def execute_dq_rules(
    db_name: str | None = Query(default=None),
    snapshot_date: str = Query(..., description="Snapshot date (YYYY-MM-DD)."),
):
    """Execute DQ rules and produce scores for one snapshot."""
    from app.agents.dq_executor_agent import run_dq_execution
    try:
        report = run_dq_execution(db_name=db_name, snapshot_date=snapshot_date)
        return {
            "status": "success",
            "db_name": db_name,
            "snapshot_date": snapshot_date,
            "message": f"Executed {report.total_rules} rules. Overall score: {report.overall_score}%",
            "summary": {
                "overall_score": report.overall_score,
                "total_rules": report.total_rules,
                "rules_passed": report.rules_passed,
                "rules_failed": report.rules_failed,
            },
        }
    except (FileNotFoundError, LookupError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
