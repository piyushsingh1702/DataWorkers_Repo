"""Database utility functions for querying SQLite metadata and data."""

import sqlite3
from pathlib import Path
from typing import Any


def get_connection(db_path: str) -> sqlite3.Connection:
    """Get a SQLite connection with row factory enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_connection(db_path: str) -> dict[str, Any]:
    """Test database connectivity. Returns status dict."""
    path = Path(db_path)
    if not path.exists():
        return {"status": "error", "message": f"Database file not found: {db_path}"}
    if not path.is_file():
        return {"status": "error", "message": f"Path is not a file: {db_path}"}
    try:
        conn = get_connection(db_path)
        conn.execute("SELECT 1")
        conn.close()
        return {"status": "success", "message": "Connection established successfully", "database": db_path}
    except sqlite3.Error as e:
        return {"status": "error", "message": f"SQLite error: {str(e)}"}


def get_all_tables(conn: sqlite3.Connection) -> list[str]:
    """Get all table names from the database."""
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def get_table_info(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    """Get column info for a table via PRAGMA table_info."""
    cursor = conn.execute(f"PRAGMA table_info('{table_name}')")
    columns = []
    for row in cursor.fetchall():
        columns.append({
            "cid": row[0],
            "name": row[1],
            "type": row[2],
            "notnull": bool(row[3]),
            "default_value": row[4],
            "pk": bool(row[5]),
        })
    return columns


def get_foreign_keys(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    """Get foreign key info for a table."""
    cursor = conn.execute(f"PRAGMA foreign_key_list('{table_name}')")
    fks = []
    for row in cursor.fetchall():
        fks.append({
            "id": row[0],
            "seq": row[1],
            "table": row[2],
            "from": row[3],
            "to": row[4],
        })
    return fks


def get_indexes(conn: sqlite3.Connection, table_name: str) -> list[dict]:
    """Get index info for a table."""
    cursor = conn.execute(f"PRAGMA index_list('{table_name}')")
    indexes = []
    for row in cursor.fetchall():
        idx_name = row[1]
        is_unique = bool(row[2])
        # Get columns in this index
        idx_info = conn.execute(f"PRAGMA index_info('{idx_name}')").fetchall()
        columns = [col[2] for col in idx_info]
        indexes.append({
            "name": idx_name,
            "unique": is_unique,
            "columns": columns,
        })
    return indexes


def get_row_count(conn: sqlite3.Connection, table_name: str) -> int:
    """Get the row count of a table."""
    cursor = conn.execute(f"SELECT COUNT(*) FROM '{table_name}'")
    return cursor.fetchone()[0]


def get_sample_values(conn: sqlite3.Connection, table_name: str, column_name: str, limit: int = 20) -> list:
    """Get sample distinct values from a column."""
    cursor = conn.execute(
        f"SELECT DISTINCT \"{column_name}\" FROM \"{table_name}\" WHERE \"{column_name}\" IS NOT NULL LIMIT ?",
        (limit,),
    )
    return [row[0] for row in cursor.fetchall()]


def get_column_stats(conn: sqlite3.Connection, table_name: str, column_name: str) -> dict:
    """Get basic statistics for a column."""
    total = conn.execute(f"SELECT COUNT(*) FROM \"{table_name}\"").fetchone()[0]
    null_count = conn.execute(
        f"SELECT COUNT(*) FROM \"{table_name}\" WHERE \"{column_name}\" IS NULL"
    ).fetchone()[0]
    distinct_count = conn.execute(
        f"SELECT COUNT(DISTINCT \"{column_name}\") FROM \"{table_name}\""
    ).fetchone()[0]

    return {
        "total_count": total,
        "null_count": null_count,
        "null_percentage": round((null_count / total * 100) if total > 0 else 0, 2),
        "distinct_count": distinct_count,
    }


def get_numeric_stats(conn: sqlite3.Connection, table_name: str, column_name: str) -> dict:
    """Get numeric statistics for a column."""
    cursor = conn.execute(f"""
        SELECT 
            MIN(CAST(\"{column_name}\" AS REAL)) as min_val,
            MAX(CAST(\"{column_name}\" AS REAL)) as max_val,
            AVG(CAST(\"{column_name}\" AS REAL)) as avg_val
        FROM \"{table_name}\"
        WHERE \"{column_name}\" IS NOT NULL
    """)
    row = cursor.fetchone()
    if row and row[0] is not None:
        return {
            "min_value": round(row[0], 4),
            "max_value": round(row[1], 4),
            "mean_value": round(row[2], 4),
        }
    return {}


def get_string_stats(conn: sqlite3.Connection, table_name: str, column_name: str) -> dict:
    """Get string length statistics for a column."""
    cursor = conn.execute(f"""
        SELECT 
            MIN(LENGTH(\"{column_name}\")) as min_len,
            MAX(LENGTH(\"{column_name}\")) as max_len,
            AVG(LENGTH(\"{column_name}\")) as avg_len
        FROM \"{table_name}\"
        WHERE \"{column_name}\" IS NOT NULL
    """)
    row = cursor.fetchone()
    if row and row[0] is not None:
        return {
            "min_length": row[0],
            "max_length": row[1],
            "avg_length": round(row[2], 2),
        }
    return {}


def get_top_values(conn: sqlite3.Connection, table_name: str, column_name: str, limit: int = 10) -> list[dict]:
    """Get top N most frequent values in a column."""
    cursor = conn.execute(f"""
        SELECT \"{column_name}\" as value, COUNT(*) as frequency
        FROM \"{table_name}\"
        WHERE \"{column_name}\" IS NOT NULL
        GROUP BY \"{column_name}\"
        ORDER BY frequency DESC
        LIMIT ?
    """, (limit,))
    return [{"value": str(row[0]), "frequency": row[1]} for row in cursor.fetchall()]


def execute_dq_query(conn: sqlite3.Connection, sql: str) -> dict:
    """Execute a DQ rule query and return results. Expects a COUNT query."""
    try:
        cursor = conn.execute(sql)
        row = cursor.fetchone()
        if row:
            return {"result": row[0], "status": "success"}
        return {"result": 0, "status": "success"}
    except sqlite3.Error as e:
        return {"result": None, "status": "error", "message": str(e)}
