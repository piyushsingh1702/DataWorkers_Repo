"""Connection Agent - Tests database connectivity."""

import logging

from app.utils.db_registry import resolve_db_path
from app.utils.db_utils import test_connection

logger = logging.getLogger(__name__)


def run_connection_test(db_name: str | None = None) -> dict:
    """
    Test database connectivity for a registered database.

    Args:
        db_name: Registered database name. Falls back to the default if omitted.

    Returns:
        Dict with status, message, and metadata.
    """
    path = resolve_db_path(db_name)
    logger.info(f"Testing connection to '{db_name or 'default'}' at: {path}")
    result = test_connection(path)
    result["db_name"] = db_name
    logger.info(f"Connection test result: {result['status']}")
    return result
