"""DQ Scores endpoints."""

import json
import logging
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.agents.qa_agent import QAScopeError, answer_question
from app.utils.db_registry import (
    list_snapshot_dates,
    load_artifact,
    load_dq_report_markdown,
)
from app.utils.llm_client import call_llm_json

router = APIRouter(prefix="/api/v1/dq-scores", tags=["DQ Scores"])
logger = logging.getLogger(__name__)

_SNAPSHOT_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _validate_snapshot(value: str, label: str) -> str:
    if not isinstance(value, str) or not _SNAPSHOT_DATE_PATTERN.match(value):
        raise HTTPException(
            status_code=400,
            detail=f"{label} must be ISO format YYYY-MM-DD (e.g. '2025-01-01').",
        )
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"{label} '{value}' is not a real date: {e}")
    return value


@router.get("/results")
def get_dq_scores(
    db_name: str | None = Query(default=None),
    snapshot_date: str = Query(..., description="Snapshot date (YYYY-MM-DD)."),
):
    """Get the DQ execution scores (JSON) for a (db_name, snapshot_date)."""
    try:
        payload = load_artifact(db_name, snapshot_date, "dq_scores")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not payload:
        raise HTTPException(status_code=404, detail="DQ scores not found. Execute DQ rules first.")
    return json.loads(payload)


@router.get("/report", response_class=PlainTextResponse)
def get_dq_report(
    db_name: str | None = Query(default=None),
    snapshot_date: str = Query(..., description="Snapshot date (YYYY-MM-DD)."),
):
    """Get the DQ report as markdown for a (db_name, snapshot_date)."""
    try:
        md = load_dq_report_markdown(db_name, snapshot_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if md is None:
        raise HTTPException(status_code=404, detail="DQ report not found. Execute DQ rules first.")
    return md


class AskRequest(BaseModel):
    table_name: str = Field(..., description="Target table to scope the answer to.")
    column_name: str | None = Field(
        default=None,
        description="Optional column to further narrow the scope. If omitted, the whole table is used.",
    )
    question: str = Field(..., description="Natural-language question about the table/column.")


@router.post("/ask")
def ask_about_entity(
    payload: AskRequest,
    db_name: str | None = Query(default=None),
    snapshot_date: str = Query(..., description="Snapshot date (YYYY-MM-DD)."),
):
    """Ask a natural-language question scoped to one (db, snapshot, table[, column])."""
    try:
        return answer_question(
            db_name=db_name,
            snapshot_date=snapshot_date,
            table=payload.table_name,
            column=payload.column_name,
            question=payload.question,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except QAScopeError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


_TREND_SYSTEM_PROMPT = (
    "You are a senior data quality analyst. You will be given a chronological "
    "series of Data Quality (DQ) score reports for a single database, one per "
    "snapshot_date. Each entry includes the overall score, per-dimension scores "
    "(Accuracy, Completeness, Consistency, Timeliness, Validity, Uniqueness), "
    "per-table scores, and aggregate pass/fail counts. Your job is to produce a "
    "rigorous, evidence-based trend analysis.\n\n"
    "Return STRICT JSON with the following shape (KEYS MUST APPEAR IN THIS ORDER):\n"
    "{\n"
    '  "summary": str,                  # 2-4 sentence executive summary\n'
    '  "overall_trend": {               # change in overall_score across the window\n'
    '      "direction": "improving"|"declining"|"stable"|"volatile",\n'
    '      "start_score": float,\n'
    '      "end_score": float,\n'
    '      "delta": float,              # end - start\n'
    '      "narrative": str             # 1-2 sentences\n'
    "  },\n"
    '  "key_findings": [str, ...],      # 3-7 specific bullet observations\n'
    '  "risks": [str, ...],             # concrete risks if trend continues\n'
    '  "recommendations": [str, ...],   # concrete next actions\n'
    '  "dimension_trends": [            # one entry per DQ dimension observed\n'
    "      {\n"
    '          "dimension": str,\n'
    '          "direction": "improving"|"declining"|"stable"|"volatile",\n'
    '          "start_score": float,\n'
    '          "end_score": float,\n'
    '          "delta": float,\n'
    '          "narrative": str\n'
    "      }\n"
    "  ],\n"
    '  "table_trends": [                # tables that materially shifted (top 5-10)\n'
    "      {\n"
    '          "table_name": str,\n'
    '          "direction": "improving"|"declining"|"stable"|"volatile",\n'
    '          "start_score": float,\n'
    '          "end_score": float,\n'
    '          "delta": float,\n'
    '          "narrative": str\n'
    "      }\n"
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- Use only the data provided. Do not invent numbers.\n"
    "- Quote actual scores in narratives where useful.\n"
    "- A delta within +/- 0.02 is 'stable'. Mixed up/down moves > 0.05 are 'volatile'.\n"
    "- Preserve the exact key order shown above.\n"
    "- Return ONLY the JSON object. No prose outside it."
)


def _compact_score_payload(payload: dict) -> dict:
    """Reduce a full DQScoreReport JSON down to only fields needed for trending."""
    return {
        "overall_score": payload.get("overall_score"),
        "total_rules": payload.get("total_rules"),
        "rules_passed": payload.get("rules_passed"),
        "rules_failed": payload.get("rules_failed"),
        "dimension_scores": [
            {
                "dimension": d.get("dimension"),
                "score": d.get("score"),
                "rules_count": d.get("rules_count"),
                "rules_passed": d.get("rules_passed"),
                "rules_failed": d.get("rules_failed"),
            }
            for d in (payload.get("dimension_scores") or [])
        ],
        "table_scores": [
            {
                "table_name": t.get("table_name"),
                "overall_score": t.get("overall_score"),
                "rules_count": t.get("rules_count"),
                "dimension_scores": [
                    {"dimension": d.get("dimension"), "score": d.get("score")}
                    for d in (t.get("dimension_scores") or [])
                ],
            }
            for t in (payload.get("table_scores") or [])
        ],
    }


@router.get("/trend")
def get_dq_trend(
    db_name: str = Query(..., description="Registered database name."),
    snapshot_date_start: str = Query(..., description="Inclusive start snapshot date (YYYY-MM-DD)."),
    snapshot_date_end: str = Query(..., description="Inclusive end snapshot date (YYYY-MM-DD)."),
):
    """Trend analysis on DQ reports between two snapshot dates (inclusive).

    Loads every DQ score artifact in ``[snapshot_date_start, snapshot_date_end]``
    for ``db_name`` and asks GPT-5.1 to produce a structured trend assessment
    covering overall score, per-dimension movement, per-table movement, key
    findings, risks, and recommendations.
    """
    start = _validate_snapshot(snapshot_date_start, "snapshot_date_start")
    end = _validate_snapshot(snapshot_date_end, "snapshot_date_end")
    if start > end:
        raise HTTPException(
            status_code=400,
            detail="snapshot_date_start must be on or before snapshot_date_end.",
        )

    all_snapshots = list_snapshot_dates(db_name)
    in_range = [s for s in all_snapshots if start <= s <= end]
    if not in_range:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No registered snapshots for db_name='{db_name}' in range "
                f"[{start}, {end}]."
            ),
        )

    series: list[dict] = []
    missing: list[str] = []
    for snap in in_range:
        raw = load_artifact(db_name, snap, "dq_scores")
        if not raw:
            missing.append(snap)
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            missing.append(snap)
            continue
        compact = _compact_score_payload(payload)
        compact["snapshot_date"] = snap
        compact["generated_at"] = payload.get("generated_at")
        series.append(compact)

    if len(series) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "Need at least 2 snapshots with persisted dq_scores in the "
                f"range to compute a trend. Found {len(series)} "
                f"(missing: {missing or 'none'}). Run /dq-rules/execute for the "
                "missing snapshots first."
            ),
        )

    user_prompt = (
        f"Database: {db_name}\n"
        f"Window: {start} to {end} (inclusive)\n"
        f"Snapshots analysed (chronological): "
        f"{', '.join(s['snapshot_date'] for s in series)}\n\n"
        "DQ score series (JSON, chronological):\n"
        f"{json.dumps(series, indent=2)}"
    )

    try:
        analysis = call_llm_json(
            system_prompt=_TREND_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.2,
            use_complex_model=True,  # GPT-5.1
        )
    except Exception as e:
        logger.exception("DQ trend LLM call failed")
        raise HTTPException(status_code=502, detail=f"LLM trend analysis failed: {e}")

    # Force a stable, human-friendly key order regardless of how the LLM
    # emitted them: summary -> overall_trend -> key_findings -> risks ->
    # recommendations -> dimension_trends -> table_trends -> (anything else).
    if isinstance(analysis, dict):
        preferred_order = (
            "summary",
            "overall_trend",
            "key_findings",
            "risks",
            "recommendations",
            "dimension_trends",
            "table_trends",
        )
        ordered = {k: analysis[k] for k in preferred_order if k in analysis}
        for k, v in analysis.items():
            if k not in ordered:
                ordered[k] = v
        analysis = ordered

    # Lightweight numeric snapshot summary for client convenience.
    overview = [
        {
            "snapshot_date": s["snapshot_date"],
            "overall_score": s.get("overall_score"),
            "rules_passed": s.get("rules_passed"),
            "rules_failed": s.get("rules_failed"),
            "total_rules": s.get("total_rules"),
        }
        for s in series
    ]

    return {
        "db_name": db_name,
        "snapshot_date_start": start,
        "snapshot_date_end": end,
        "snapshots_analysed": [s["snapshot_date"] for s in series],
        "snapshots_missing_scores": missing,
        "overview": overview,
        "model": "gpt-5.1",
        "analysis": analysis,
    }
