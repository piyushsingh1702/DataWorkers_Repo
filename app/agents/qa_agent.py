"""Q&A Agent - Answers natural-language questions about a single table or column.

Pulls every persisted artifact from ``dq_admin`` (technical catalogue, glossary,
classification report, DQ rules, DQ scores) and **strictly filters** them to
the requested table (and optionally column) before handing them to the LLM.
This guarantees the answer is scoped to the requested entity and never mixes
in data from siblings.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.models.catalogue import TechnicalCatalogue
from app.models.classification import ClassificationReport
from app.models.dq_rules import DQRuleSet, DQScoreReport
from app.models.glossary import DataGlossary
from app.utils.db_registry import load_artifact
from app.utils.llm_client import call_llm

logger = logging.getLogger(__name__)


QA_SYSTEM_PROMPT = """You are a data quality and metadata expert assistant.

You will be given:
1. A scoped CONTEXT containing all metadata, profiling, classification, DQ rules, and DQ scores for a SINGLE table (and optionally a single column).
2. A user QUESTION about that specific table/column.

Strict rules:
- Answer ONLY using the provided CONTEXT. Do not invent facts.
- The CONTEXT has already been filtered to the target table/column. Do NOT discuss any other table or column, even if asked.
- If the answer is not present in the CONTEXT, say so explicitly and list what additional artifact would be needed.
- Be concise, structured (use short sections or bullet points), and quote concrete numbers/examples from the CONTEXT.
- When relevant, cover: business meaning, sensitivity/CDE status, profiling stats, applicable DQ rules, and DQ rule outcomes.
"""


class QAScopeError(LookupError):
    """Raised when the requested table or column cannot be found in any artifact."""


def _filter_catalogue(catalogue: TechnicalCatalogue, table: str, column: str | None) -> dict | None:
    for t in catalogue.tables:
        if t.name == table:
            data = t.model_dump()
            if column is not None:
                data["columns"] = [c for c in data["columns"] if c["name"] == column]
                data["foreign_keys"] = [fk for fk in data["foreign_keys"] if fk["column"] == column]
                data["primary_keys"] = [pk for pk in data["primary_keys"] if pk == column]
            return data
    return None


def _filter_glossary(glossary: DataGlossary, table: str, column: str | None) -> list[dict]:
    return [
        e.model_dump()
        for e in glossary.entries
        if e.table_name == table and (column is None or e.column_name == column)
    ]


def _filter_classifications(report: ClassificationReport, table: str, column: str | None) -> list[dict]:
    return [
        c.model_dump()
        for c in report.classifications
        if c.table_name == table and (column is None or c.column_name == column)
    ]


def _filter_rules(rule_set: DQRuleSet, table: str, column: str | None) -> list[dict]:
    return [
        r.model_dump()
        for r in rule_set.rules
        if r.table_name == table and (column is None or r.column_name == column or r.column_name is None)
    ]


def _filter_scores(report: DQScoreReport, table: str, column: str | None) -> dict[str, Any]:
    rule_results = [
        rr.model_dump()
        for rr in report.rule_results
        if rr.table_name == table and (column is None or rr.column_name == column or rr.column_name is None)
    ]
    table_score = next(
        (ts.model_dump() for ts in report.table_scores if ts.table_name == table),
        None,
    )
    return {"table_score": table_score, "rule_results": rule_results}


def _load_optional(model_cls, db_name: str | None, kind: str):
    payload = load_artifact(db_name, kind)
    if not payload:
        return None
    return model_cls.model_validate_json(payload)


def build_scoped_context(
    db_name: str | None,
    table: str,
    column: str | None,
) -> dict[str, Any]:
    """Load every artifact and return a dict scoped to ``table`` (+ optional ``column``).

    Raises ``QAScopeError`` if neither a catalogue entry nor a glossary entry
    exists for the requested scope (i.e. nothing to talk about).
    """
    catalogue = _load_optional(TechnicalCatalogue, db_name, "technical_catalogue")
    glossary = _load_optional(DataGlossary, db_name, "data_glossary")
    classification = _load_optional(ClassificationReport, db_name, "classification_report")
    rules = _load_optional(DQRuleSet, db_name, "dq_rules")
    scores = _load_optional(DQScoreReport, db_name, "dq_scores")

    ctx: dict[str, Any] = {
        "scope": {"db_name": db_name, "table": table, "column": column},
        "technical_catalogue": _filter_catalogue(catalogue, table, column) if catalogue else None,
        "data_glossary_entries": _filter_glossary(glossary, table, column) if glossary else [],
        "classifications": _filter_classifications(classification, table, column) if classification else [],
        "dq_rules": _filter_rules(rules, table, column) if rules else [],
        "dq_scores": _filter_scores(scores, table, column) if scores else None,
    }

    found = (
        ctx["technical_catalogue"] is not None
        or ctx["data_glossary_entries"]
        or ctx["classifications"]
        or ctx["dq_rules"]
        or (ctx["dq_scores"] and (ctx["dq_scores"]["table_score"] or ctx["dq_scores"]["rule_results"]))
    )
    if not found:
        scope_str = f"{table}.{column}" if column else table
        raise QAScopeError(
            f"No metadata or DQ artifacts found for '{scope_str}' in db '{db_name or 'default'}'. "
            "Ensure the table/column name is correct and that discovery/profiling have been run."
        )
    return ctx


def answer_question(
    db_name: str | None,
    table: str,
    column: str | None,
    question: str,
) -> dict[str, Any]:
    """Answer ``question`` strictly within the scope of ``table`` (and optionally ``column``)."""
    if not question or not question.strip():
        raise ValueError("question must be a non-empty string")

    context = build_scoped_context(db_name, table, column)

    scope_label = f"table '{table}'" + (f", column '{column}'" if column else "")
    user_prompt = (
        f"Scope: {scope_label} in database '{db_name or 'default'}'.\n\n"
        f"CONTEXT (JSON, already filtered to scope above):\n"
        f"```json\n{json.dumps(context, indent=2, default=str)}\n```\n\n"
        f"QUESTION: {question.strip()}\n\n"
        f"Answer using ONLY this CONTEXT. Do not reference other tables or columns."
    )

    logger.info(f"Q&A on {scope_label} (db='{db_name or 'default'}'): {question[:120]}")
    answer = call_llm(QA_SYSTEM_PROMPT, user_prompt, temperature=0.2)

    return {
        "db_name": db_name,
        "table": table,
        "column": column,
        "question": question,
        "answer": answer,
        "context_summary": {
            "has_catalogue": context["technical_catalogue"] is not None,
            "glossary_entries": len(context["data_glossary_entries"]),
            "classifications": len(context["classifications"]),
            "dq_rules": len(context["dq_rules"]),
            "dq_rule_results": (
                len(context["dq_scores"]["rule_results"]) if context["dq_scores"] else 0
            ),
        },
    }
