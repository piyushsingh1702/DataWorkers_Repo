"""Orchestrator - Coordinates the full pipeline execution."""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from enum import Enum

from app.agents.connection_agent import run_connection_test
from app.agents.discovery_agent import run_discovery
from app.agents.profiling_agent import run_profiling
from app.agents.classification_agent import run_classification
from app.agents.dq_rules_agent import run_dq_rules_generation
from app.agents.dq_executor_agent import run_dq_execution
from app.database.setup_mortgage_sample_db import create_mortgage_database

logger = logging.getLogger(__name__)


class PipelineStatus(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineState:
    """Tracks pipeline execution state."""

    def __init__(self):
        self.status: PipelineStatus = PipelineStatus.NOT_STARTED
        self.current_step: str = ""
        self.steps_completed: list[str] = []
        self.error: str | None = None
        self.started_at: str | None = None
        self.completed_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "current_step": self.current_step,
            "steps_completed": self.steps_completed,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# Global pipeline state
pipeline_state = PipelineState()


def run_full_pipeline(
    db_name: str | None = None,
    snapshot_date: str | None = None,
    description: str | None = None,
    properties: dict | None = None,
    setup_database: bool = True,
) -> dict:
    """Run the full DQ pipeline against a (db_name, snapshot_date) pair.

    Args:
        db_name: Registered database name. The DB is (re)created when
            ``setup_database=True`` with all default snapshots.
        snapshot_date: REQUIRED. The data snapshot to run discovery / profiling /
            classification / DQ rule generation & execution against.
        description: Optional description stored in the dq_admin registry.
        properties: Optional metadata stored in the dq_admin registry.
        setup_database: When True (default), recreate the sample DB before
            running the pipeline. Set False to run against an existing DB whose
            snapshots are already populated.

    Returns summary of results.
    """
    if not snapshot_date:
        raise ValueError("snapshot_date is required (e.g. '2025-01-01').")

    global pipeline_state
    pipeline_state = PipelineState()
    pipeline_state.status = PipelineStatus.RUNNING
    pipeline_state.started_at = datetime.now(timezone.utc).isoformat()

    try:
        if setup_database:
            # Step 1: Load this snapshot. If it already exists, only its rows
            # are replaced; other snapshots in the same DB are preserved.
            pipeline_state.current_step = "database_setup"
            logger.info(
                f"Pipeline Step 1: Loading snapshot '{snapshot_date}' into "
                f"database '{db_name or 'default'}'"
            )
            create_mortgage_database(
                db_name=db_name,
                snapshot_date=snapshot_date,
                description=description,
                properties=properties,
            )
            pipeline_state.steps_completed.append("database_setup")

        # Step 2: Connection test
        pipeline_state.current_step = "connection_test"
        logger.info("Pipeline Step 2: Testing connection")
        conn_result = run_connection_test(db_name, snapshot_date=snapshot_date)
        if conn_result["status"] != "success":
            raise RuntimeError(f"Connection failed: {conn_result['message']}")
        pipeline_state.steps_completed.append("connection_test")

        # Step 3 + 4: Discovery and Profiling run in parallel.
        # They are fully independent (both read directly from the source DB,
        # neither consumes the other's artifact). SQLite handles concurrent
        # readers, and each agent opens its own connection.
        pipeline_state.current_step = "discovery+profiling"
        logger.info("Pipeline Step 3+4: Running discovery and profiling in parallel")
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline") as ex:
            discovery_future = ex.submit(run_discovery, db_name, snapshot_date=snapshot_date)
            profiling_future = ex.submit(run_profiling, db_name, snapshot_date=snapshot_date)
            # .result() re-raises any exception raised inside the worker thread.
            catalogue = discovery_future.result()
            pipeline_state.steps_completed.append("discovery")
            glossary = profiling_future.result()
            pipeline_state.steps_completed.append("profiling")

        # Step 5: Classification
        pipeline_state.current_step = "classification"
        logger.info("Pipeline Step 5: Running classification")
        classification = run_classification(glossary, db_name=db_name, snapshot_date=snapshot_date)
        pipeline_state.steps_completed.append("classification")

        # Step 6: DQ Rules Generation
        pipeline_state.current_step = "dq_rules_generation"
        logger.info("Pipeline Step 6: Generating DQ rules")
        rule_set = run_dq_rules_generation(
            catalogue, glossary, classification, db_name=db_name, snapshot_date=snapshot_date
        )
        pipeline_state.steps_completed.append("dq_rules_generation")

        # Step 7: DQ Execution
        pipeline_state.current_step = "dq_execution"
        logger.info("Pipeline Step 7: Executing DQ rules")
        score_report = run_dq_execution(rule_set, db_name=db_name, snapshot_date=snapshot_date)
        pipeline_state.steps_completed.append("dq_execution")

        pipeline_state.status = PipelineStatus.COMPLETED
        pipeline_state.current_step = ""
        pipeline_state.completed_at = datetime.now(timezone.utc).isoformat()

        return {
            "status": "completed",
            "db_name": db_name,
            "snapshot_date": snapshot_date,
            "overall_dq_score": score_report.overall_score,
            "total_rules": score_report.total_rules,
            "rules_passed": score_report.rules_passed,
            "rules_failed": score_report.rules_failed,
            "steps_completed": pipeline_state.steps_completed,
        }

    except Exception as e:
        pipeline_state.status = PipelineStatus.FAILED
        pipeline_state.error = str(e)
        pipeline_state.completed_at = datetime.now(timezone.utc).isoformat()
        logger.error(f"Pipeline failed at step '{pipeline_state.current_step}': {e}")
        raise


def get_pipeline_status() -> dict:
    """Get current pipeline execution status."""
    return pipeline_state.to_dict()
