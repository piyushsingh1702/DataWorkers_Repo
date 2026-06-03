"""Connection Agent - Tests database connectivity."""

import logging

from app.utils.db_registry import resolve_db_path
from app.utils.db_utils import test_connection

logger = logging.getLogger(__name__)


def run_connection_test(db_name: str | None = None, snapshot_date: str | None = None) -> dict:
    """Test database connectivity and (if provided) verify the snapshot exists."""
    path = resolve_db_path(db_name)
    logger.info(f"Testing connection to '{db_name or 'default'}' at: {path} (snapshot={snapshot_date})")
    result = test_connection(path)
    result["db_name"] = db_name
    result["snapshot_date"] = snapshot_date

    if result["status"] == "success" and snapshot_date:
        from app.utils.db_registry import list_snapshot_dates
        available = list_snapshot_dates(db_name) if db_name else []
        if available and snapshot_date not in available:
            result["status"] = "error"
            result["message"] = (
                f"snapshot_date '{snapshot_date}' is not registered for db '{db_name}'. "
                f"Available: {available}"
            )
        else:
            result["available_snapshots"] = available

    logger.info(f"Connection test result: {result['status']}")
    return result
