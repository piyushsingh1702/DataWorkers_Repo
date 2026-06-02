"""DQ Scores endpoints."""

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app.agents.qa_agent import QAScopeError, answer_question
from app.utils.db_registry import load_artifact, load_dq_report_markdown

router = APIRouter(prefix="/api/v1/dq-scores", tags=["DQ Scores"])


@router.get("/results")
def get_dq_scores(db_name: str | None = Query(default=None)):
    """Get the DQ execution scores (JSON) for a database."""
    payload = load_artifact(db_name, "dq_scores")
    if not payload:
        raise HTTPException(status_code=404, detail="DQ scores not found. Execute DQ rules first.")
    return json.loads(payload)


@router.get("/report", response_class=PlainTextResponse)
def get_dq_report(db_name: str | None = Query(default=None)):
    """Get the DQ report as markdown for a database."""
    md = load_dq_report_markdown(db_name)
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
):
    """Ask a natural-language question scoped strictly to one table or column.

    The endpoint pulls all persisted artifacts (catalogue, glossary,
    classification, DQ rules, DQ scores) for the given database, filters them
    to the requested table (and optionally column), and asks the LLM to answer
    using only that scoped context. Results never mix in data from other
    tables/columns.
    """
    try:
        return answer_question(
            db_name=db_name,
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
