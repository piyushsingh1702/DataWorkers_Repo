"""Connection Agent - Tests database connectivity."""

import logging

from app.config.settings import settings
from app.utils.db_utils import test_connection

logger = logging.getLogger(__name__)


def run_connection_test(db_path: str | None = None) -> dict:
    """
    Test database connectivity.
    
    Args:
        db_path: Optional override for database path. Uses settings default if not provided.
    
    Returns:
        Dict with status, message, and metadata.
    """
    path = db_path or settings.database_path
    logger.info(f"Testing connection to: {path}")
    result = test_connection(path)
    logger.info(f"Connection test result: {result['status']}")
    return result
