"""Orchestrator - Coordinates the full pipeline execution."""

import logging
from datetime import datetime, timezone
from enum import Enum

from app.agents.connection_agent import run_connection_test
from app.agents.discovery_agent import run_discovery
from app.agents.profiling_agent import run_profiling
from app.agents.classification_agent import run_classification
from app.agents.dq_rules_agent import run_dq_rules_generation
from app.agents.dq_executor_agent import run_dq_execution
from app.database.setup_sample_db import create_sample_database

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


def run_full_pipeline(db_path: str | None = None) -> dict:
    """
    Run the full data quality pipeline end-to-end.
    Returns summary of results.
    """
    global pipeline_state
    pipeline_state = PipelineState()
    pipeline_state.status = PipelineStatus.RUNNING
    pipeline_state.started_at = datetime.now(timezone.utc).isoformat()

    try:
        # Step 1: Setup database
        pipeline_state.current_step = "database_setup"
        logger.info("Pipeline Step 1: Setting up sample database")
        create_sample_database()
        pipeline_state.steps_completed.append("database_setup")

        # Step 2: Connection test
        pipeline_state.current_step = "connection_test"
        logger.info("Pipeline Step 2: Testing connection")
        conn_result = run_connection_test(db_path)
        if conn_result["status"] != "success":
            raise RuntimeError(f"Connection failed: {conn_result['message']}")
        pipeline_state.steps_completed.append("connection_test")

        # Step 3: Discovery
        pipeline_state.current_step = "discovery"
        logger.info("Pipeline Step 3: Running discovery")
        catalogue = run_discovery(db_path)
        pipeline_state.steps_completed.append("discovery")

        # Step 4: Profiling
        pipeline_state.current_step = "profiling"
        logger.info("Pipeline Step 4: Running profiling")
        glossary = run_profiling(db_path)
        pipeline_state.steps_completed.append("profiling")

        # Step 5: Classification
        pipeline_state.current_step = "classification"
        logger.info("Pipeline Step 5: Running classification")
        classification = run_classification(glossary)
        pipeline_state.steps_completed.append("classification")

        # Step 6: DQ Rules Generation
        pipeline_state.current_step = "dq_rules_generation"
        logger.info("Pipeline Step 6: Generating DQ rules")
        rule_set = run_dq_rules_generation(catalogue, glossary, classification)
        pipeline_state.steps_completed.append("dq_rules_generation")

        # Step 7: DQ Execution
        pipeline_state.current_step = "dq_execution"
        logger.info("Pipeline Step 7: Executing DQ rules")
        score_report = run_dq_execution(rule_set, db_path)
        pipeline_state.steps_completed.append("dq_execution")

        pipeline_state.status = PipelineStatus.COMPLETED
        pipeline_state.current_step = ""
        pipeline_state.completed_at = datetime.now(timezone.utc).isoformat()

        return {
            "status": "completed",
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
