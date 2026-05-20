"""Classification Agent - Classifies data sensitivity and identifies CDEs."""

import logging
from datetime import datetime, timezone

from app.config.settings import settings
from app.models.classification import ClassificationReport, ColumnClassification
from app.models.glossary import DataGlossary
from app.utils.llm_client import call_llm_json
from app.utils.prompts import CLASSIFICATION_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def run_classification(glossary: DataGlossary | None = None) -> ClassificationReport:
    """
    Classify columns by sensitivity and identify Critical Data Elements.
    Uses data glossary as input context for better classification.
    """
    # Load glossary from file if not provided
    if glossary is None:
        glossary_path = settings.outputs_path / "data_glossary.json"
        if not glossary_path.exists():
            raise FileNotFoundError("Data glossary not found. Run profiling first.")
        glossary = DataGlossary.model_validate_json(glossary_path.read_text())

    logger.info(f"Running classification on {glossary.total_entries} columns")

    # Process in batches per table
    all_classifications = []
    tables = {}
    for entry in glossary.entries:
        tables.setdefault(entry.table_name, []).append(entry)

    for table_name, entries in tables.items():
        classifications = _classify_table(table_name, entries)
        all_classifications.extend(classifications)

    # Compute summary
    total_columns = len(all_classifications)
    cde_count = sum(1 for c in all_classifications if c.is_cde)
    classification_summary = {}
    for c in all_classifications:
        classification_summary[c.classification] = classification_summary.get(c.classification, 0) + 1

    report = ClassificationReport(
        database_name=glossary.database_name,
        classifications=all_classifications,
        total_columns=total_columns,
        cde_count=cde_count,
        cde_percentage=round((cde_count / total_columns * 100) if total_columns > 0 else 0, 2),
        classification_summary=classification_summary,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # Save output
    output_path = settings.outputs_path / "classification_report.json"
    output_path.write_text(report.model_dump_json(indent=2))
    logger.info(f"Classification report saved to {output_path}")

    return report


def _classify_table(table_name: str, entries) -> list[ColumnClassification]:
    """Use LLM to classify columns in a table."""
    # Build context for LLM
    columns_info = []
    for entry in entries:
        info = (
            f"Column: {entry.column_name}\n"
            f"  Description: {entry.business_description}\n"
            f"  Domain: {entry.data_domain}\n"
            f"  Is PII: {entry.is_pii}\n"
            f"  Is Enumeration: {entry.is_enumeration}\n"
            f"  Null%: {entry.profile.null_percentage}\n"
            f"  Sample values: {entry.profile.sample_values[:5]}"
        )
        columns_info.append(info)

    user_prompt = (
        f"Table: {table_name}\n"
        f"Total columns in database: ~{len(entries) * 10} (aim for ~20% CDE overall)\n\n"
        f"Columns to classify:\n" + "\n\n".join(columns_info)
    )

    try:
        result = call_llm_json(CLASSIFICATION_SYSTEM_PROMPT, user_prompt)
        llm_classifications = {c["column_name"]: c for c in result.get("classifications", [])}
    except Exception as e:
        logger.warning(f"LLM classification failed for {table_name}: {e}")
        llm_classifications = {}

    classifications = []
    for entry in entries:
        llm_data = llm_classifications.get(entry.column_name, {})
        classifications.append(ColumnClassification(
            table_name=table_name,
            column_name=entry.column_name,
            classification=llm_data.get("classification", "Internal"),
            is_cde=llm_data.get("is_cde", False),
            cde_rationale=llm_data.get("cde_rationale", ""),
            classification_rationale=llm_data.get("classification_rationale", ""),
        ))

    return classifications
