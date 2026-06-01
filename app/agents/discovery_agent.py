"""Discovery Agent - Builds technical catalogue from database metadata."""

import json
import logging
from datetime import datetime, timezone

from app.config.settings import settings
from app.models.catalogue import ColumnInfo, ForeignKey, TableInfo, TechnicalCatalogue
from app.utils.db_utils import (
    get_connection, get_all_tables, get_table_info,
    get_foreign_keys, get_indexes, get_row_count,
)
from app.utils.llm_client import call_llm_json
from app.utils.prompts import DISCOVERY_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


def run_discovery(db_path: str | None = None) -> TechnicalCatalogue:
    """
    Discover database metadata and build a technical catalogue.
    Uses AI to generate descriptions for tables and columns.
    """
    path = db_path or settings.database_path
    logger.info(f"Running discovery on: {path}")

    conn = get_connection(path)
    try:
        tables = get_all_tables(conn)
        table_infos = []
        total_columns = 0

        for table_name in tables:
            columns_raw = get_table_info(conn, table_name)
            fks_raw = get_foreign_keys(conn, table_name)
            indexes = get_indexes(conn, table_name)
            row_count = get_row_count(conn, table_name)

            # Determine unique columns from indexes
            unique_columns = set()
            for idx in indexes:
                if idx["unique"] and len(idx["columns"]) == 1:
                    unique_columns.add(idx["columns"][0])

            columns = []
            primary_keys = []
            for col in columns_raw:
                is_pk = col["pk"]
                if is_pk:
                    primary_keys.append(col["name"])
                columns.append(ColumnInfo(
                    name=col["name"],
                    data_type=col["type"] or "TEXT",
                    nullable=not col["notnull"],
                    default_value=col["default_value"],
                    is_primary_key=is_pk,
                    is_unique=col["name"] in unique_columns,
                ))

            foreign_keys = [
                ForeignKey(
                    column=fk["from"],
                    references_table=fk["table"],
                    references_column=fk["to"],
                )
                for fk in fks_raw
            ]

            table_infos.append(TableInfo(
                name=table_name,
                row_count=row_count,
                columns=columns,
                primary_keys=primary_keys,
                foreign_keys=foreign_keys,
            ))
            total_columns += len(columns)

        # Use AI to generate descriptions
        table_infos = _enrich_with_descriptions(table_infos)

        catalogue = TechnicalCatalogue(
            database_name=path,
            tables=table_infos,
            total_tables=len(table_infos),
            total_columns=total_columns,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Save output
        output_path = settings.outputs_path / "technical_catalogue.json"
        output_path.write_text(catalogue.model_dump_json(indent=2))
        logger.info(f"Technical catalogue saved to {output_path}")

        return catalogue
    finally:
        conn.close()


def _enrich_with_descriptions(table_infos: list[TableInfo]) -> list[TableInfo]:
    """Use LLM to generate descriptions for tables and columns."""
    # Build context for LLM
    metadata_summary = []
    for table in table_infos:
        cols_desc = ", ".join([f"{c.name} ({c.data_type})" for c in table.columns])
        fks_desc = ", ".join([f"{fk.column} -> {fk.references_table}.{fk.references_column}" for fk in table.foreign_keys])
        metadata_summary.append(
            f"Table: {table.name} ({table.row_count} rows)\n"
            f"  Columns: {cols_desc}\n"
            f"  PKs: {', '.join(table.primary_keys)}\n"
            f"  FKs: {fks_desc or 'None'}"
        )

    user_prompt = "Generate descriptions for these database tables and columns:\n\n" + "\n\n".join(metadata_summary)

    try:
        result = call_llm_json(DISCOVERY_SYSTEM_PROMPT, user_prompt)
        tables_list = result.get("tables", []) if isinstance(result, dict) else result
        descriptions = {t["table_name"]: t for t in tables_list}

        for table in table_infos:
            if table.name in descriptions:
                table.description = descriptions[table.name].get("description", "")
                col_descs = {c["column_name"]: c["description"] for c in descriptions[table.name].get("columns", [])}
                for col in table.columns:
                    if col.name in col_descs:
                        col.description = col_descs[col.name]
    except Exception as e:
        logger.warning(f"LLM enrichment failed, continuing without descriptions: {e}")

    return table_infos
