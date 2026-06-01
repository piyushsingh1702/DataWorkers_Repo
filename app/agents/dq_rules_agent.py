"""DQ Rules Agent - Generates data quality rules using AI."""

import logging
from datetime import datetime, timezone

from app.config.settings import settings
from app.models.catalogue import TechnicalCatalogue
from app.models.classification import ClassificationReport
from app.models.dq_rules import DQRule, DQRuleSet
from app.models.glossary import DataGlossary
from app.utils.llm_client import call_llm_json
from app.utils.prompts import DQ_RULES_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def run_dq_rules_generation(
    catalogue: TechnicalCatalogue | None = None,
    glossary: DataGlossary | None = None,
    classification: ClassificationReport | None = None,
) -> DQRuleSet:
    """
    Generate data quality rules based on catalogue, glossary, and classification.
    All rules are AI-generated and mapped to DQ dimensions.
    """
    # Load from files if not provided
    if catalogue is None:
        cat_path = settings.outputs_path / "technical_catalogue.json"
        if not cat_path.exists():
            raise FileNotFoundError("Technical catalogue not found. Run discovery first.")
        catalogue = TechnicalCatalogue.model_validate_json(cat_path.read_text())

    if glossary is None:
        glos_path = settings.outputs_path / "data_glossary.json"
        if not glos_path.exists():
            raise FileNotFoundError("Data glossary not found. Run profiling first.")
        glossary = DataGlossary.model_validate_json(glos_path.read_text())

    if classification is None:
        class_path = settings.outputs_path / "classification_report.json"
        if not class_path.exists():
            raise FileNotFoundError("Classification report not found. Run classification first.")
        classification = ClassificationReport.model_validate_json(class_path.read_text())

    logger.info("Generating DQ rules using AI agent")

    # Build CDE lookup
    cde_columns = set()
    for c in classification.classifications:
        if c.is_cde:
            cde_columns.add(f"{c.table_name}.{c.column_name}")

    # Generate rules per table
    all_rules = []
    for table in catalogue.tables:
        table_rules = _generate_rules_for_table(table, glossary, classification, cde_columns)
        all_rules.extend(table_rules)

    # Compute summaries
    rules_by_dimension = {}
    rules_by_type = {}
    for rule in all_rules:
        rules_by_dimension[rule.dimension] = rules_by_dimension.get(rule.dimension, 0) + 1
        rules_by_type[rule.rule_type] = rules_by_type.get(rule.rule_type, 0) + 1

    rule_set = DQRuleSet(
        database_name=catalogue.database_name,
        rules=all_rules,
        total_rules=len(all_rules),
        rules_by_dimension=rules_by_dimension,
        rules_by_type=rules_by_type,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # Save output
    output_path = settings.outputs_path / "dq_rules.json"
    output_path.write_text(rule_set.model_dump_json(indent=2))
    logger.info(f"DQ rules saved to {output_path} ({len(all_rules)} rules)")

    return rule_set


def _generate_rules_for_table(table, glossary, classification, cde_columns) -> list[DQRule]:
    """Generate DQ rules for a single table using LLM."""
    # Build context
    columns_context = []
    for col in table.columns:
        col_key = f"{table.name}.{col.name}"
        is_cde = col_key in cde_columns

        # Find glossary entry
        glossary_desc = ""
        for entry in glossary.entries:
            if entry.table_name == table.name and entry.column_name == col.name:
                glossary_desc = entry.business_description
                break

        # Find classification
        col_classification = "Internal"
        for c in classification.classifications:
            if c.table_name == table.name and c.column_name == col.name:
                col_classification = c.classification
                break

        columns_context.append(
            f"  - {col.name} ({col.data_type}): {glossary_desc} "
            f"[nullable={col.nullable}, pk={col.is_primary_key}, "
            f"classification={col_classification}, CDE={is_cde}]"
        )

    fk_context = ""
    if table.foreign_keys:
        fk_context = "\nForeign Keys:\n" + "\n".join(
            f"  - {fk.column} -> {fk.references_table}.{fk.references_column}"
            for fk in table.foreign_keys
        )

    user_prompt = (
        f"Generate DQ rules for table: {table.name} ({table.row_count} rows)\n\n"
        f"Columns:\n" + "\n".join(columns_context) + fk_context +
        f"\n\nGenerate 3-5 rules covering multiple DQ dimensions. "
        f"Prioritize CDE columns for business rules. "
        f"Use rule IDs starting with DQ_{table.name.upper()}_"
    )

    try:
        result = call_llm_json(DQ_RULES_SYSTEM_PROMPT, user_prompt, use_complex_model=True)
        rules_data = result.get("rules", []) if isinstance(result, dict) else result
    except Exception as e:
        logger.warning(f"LLM rule generation failed for {table.name}: {e}")
        rules_data = []

    rules = []
    for rule_data in rules_data:
        try:
            rule = DQRule(
                rule_id=rule_data["rule_id"],
                rule_name=rule_data["rule_name"],
                dimension=rule_data["dimension"],
                table_name=rule_data.get("table_name", table.name),
                column_name=rule_data.get("column_name"),
                rule_type=rule_data.get("rule_type", "technical"),
                description=rule_data["description"],
                sql_query=rule_data["sql_query"],
                threshold=rule_data.get("threshold", 0.95),
                severity=rule_data.get("severity", "medium"),
                cde_linked=rule_data.get("cde_linked", False),
            )
            rules.append(rule)
        except (KeyError, ValueError) as e:
            logger.warning(f"Invalid rule data: {e}")

    return rules
