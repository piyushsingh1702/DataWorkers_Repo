"""Profiling Agent - Profiles data and generates business glossary."""

import logging
from datetime import datetime, timezone

from app.config.settings import settings
from app.models.glossary import ColumnProfile, DataGlossary, GlossaryEntry
from app.utils.db_utils import (
    get_connection, get_all_tables, get_table_info,
    get_column_stats, get_numeric_stats, get_string_stats,
    get_sample_values, get_top_values, get_row_count,
)
from app.utils.llm_client import call_llm_json
from app.utils.prompts import PROFILING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# SQLite types that are numeric
NUMERIC_TYPES = {"INTEGER", "REAL", "NUMERIC", "FLOAT", "DOUBLE", "DECIMAL"}


def run_profiling(db_path: str | None = None) -> DataGlossary:
    """
    Profile all columns and generate a data glossary with AI-enriched descriptions.
    """
    path = db_path or settings.database_path
    logger.info(f"Running data profiling on: {path}")

    conn = get_connection(path)
    try:
        tables = get_all_tables(conn)
        all_profiles: list[ColumnProfile] = []

        for table_name in tables:
            columns = get_table_info(conn, table_name)
            row_count = get_row_count(conn, table_name)

            for col in columns:
                col_name = col["name"]
                col_type = (col["type"] or "TEXT").upper()

                # Basic stats
                stats = get_column_stats(conn, table_name, col_name)
                sample_vals = get_sample_values(conn, table_name, col_name, limit=20)
                top_vals = get_top_values(conn, table_name, col_name, limit=10)

                profile = ColumnProfile(
                    table_name=table_name,
                    column_name=col_name,
                    data_type=col_type,
                    total_count=stats["total_count"],
                    null_count=stats["null_count"],
                    null_percentage=stats["null_percentage"],
                    distinct_count=stats["distinct_count"],
                    sample_values=[str(v) for v in sample_vals[:10]],
                    top_values=top_vals,
                )

                # Numeric stats
                if any(nt in col_type for nt in NUMERIC_TYPES):
                    num_stats = get_numeric_stats(conn, table_name, col_name)
                    if num_stats:
                        profile.min_value = num_stats.get("min_value")
                        profile.max_value = num_stats.get("max_value")
                        profile.mean_value = num_stats.get("mean_value")

                # String stats
                if "TEXT" in col_type or "CHAR" in col_type or col_type == "":
                    str_stats = get_string_stats(conn, table_name, col_name)
                    if str_stats:
                        profile.min_length = str_stats.get("min_length")
                        profile.max_length = str_stats.get("max_length")
                        profile.avg_length = str_stats.get("avg_length")

                all_profiles.append(profile)

        # Use AI to generate business glossary entries
        entries = _generate_glossary_entries(all_profiles)

        glossary = DataGlossary(
            database_name=path,
            entries=entries,
            total_entries=len(entries),
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Save output
        output_path = settings.outputs_path / "data_glossary.json"
        output_path.write_text(glossary.model_dump_json(indent=2))
        logger.info(f"Data glossary saved to {output_path}")

        return glossary
    finally:
        conn.close()


def _generate_glossary_entries(profiles: list[ColumnProfile]) -> list[GlossaryEntry]:
    """Use LLM to generate business descriptions for profiled columns."""
    # Process in batches per table to avoid token limits
    entries = []
    tables = {}
    for p in profiles:
        tables.setdefault(p.table_name, []).append(p)

    for table_name, table_profiles in tables.items():
        batch_entries = _process_table_batch(table_name, table_profiles)
        entries.extend(batch_entries)

    return entries


def _process_table_batch(table_name: str, profiles: list[ColumnProfile]) -> list[GlossaryEntry]:
    """Process one table's columns through the LLM."""
    # Build profile summary for LLM
    profile_summaries = []
    for p in profiles:
        summary = (
            f"Column: {p.column_name} (type: {p.data_type})\n"
            f"  Nulls: {p.null_percentage}%, Distinct: {p.distinct_count}/{p.total_count}\n"
            f"  Sample values: {p.sample_values[:5]}\n"
            f"  Top values: {[v['value'] for v in p.top_values[:5]]}"
        )
        if p.min_value is not None:
            summary += f"\n  Numeric range: {p.min_value} to {p.max_value}, mean: {p.mean_value}"
        if p.min_length is not None:
            summary += f"\n  String length: {p.min_length} to {p.max_length}, avg: {p.avg_length}"
        profile_summaries.append(summary)

    user_prompt = (
        f"Table: {table_name}\n\n"
        f"Column profiles:\n" + "\n\n".join(profile_summaries)
    )

    try:
        result = call_llm_json(PROFILING_SYSTEM_PROMPT, user_prompt)
        llm_entries = {e["column_name"]: e for e in result.get("entries", [])}
    except Exception as e:
        logger.warning(f"LLM glossary generation failed for {table_name}: {e}")
        llm_entries = {}

    entries = []
    for p in profiles:
        llm_data = llm_entries.get(p.column_name, {})
        entries.append(GlossaryEntry(
            table_name=p.table_name,
            column_name=p.column_name,
            business_description=llm_data.get("business_description", f"Column {p.column_name} in {p.table_name}"),
            data_domain=llm_data.get("data_domain", "Unknown"),
            is_enumeration=llm_data.get("is_enumeration", p.distinct_count <= 20 and p.total_count > 50),
            enum_values=p.sample_values if (llm_data.get("is_enumeration") or (p.distinct_count <= 20 and p.total_count > 50)) else [],
            is_pii=llm_data.get("is_pii", False),
            profile=p,
        ))

    return entries
