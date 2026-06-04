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
from app.config.settings import settings
from app.database.setup_mortgage_sample_db import create_mortgage_database
from app.utils.completeness import (
    STAGE_CLASSIFICATION,
    STAGE_DISCOVERY,
    STAGE_DQ_EXECUTION,
    STAGE_DQ_RULES,
    STAGE_PROFILING,
    CompletenessError,
    CompletenessReport,
    check_completeness,
)
from app.utils.interaction_log import log_gate, log_halt, log_handoff

logger = logging.getLogger(__name__)


# Default minimum completeness score required to let an upstream artifact
# flow into the next agent. Overridable via the
# ``completeness_threshold`` setting (env var ``COMPLETENESS_THRESHOLD``).
DEFAULT_COMPLETENESS_THRESHOLD = 0.8


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
        # Completeness checks attached to each stage's upstream artifact.
        self.completeness_reports: list[dict] = []
        # Convenience: which stage (if any) tripped the completeness gate.
        self.blocked_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "current_step": self.current_step,
            "steps_completed": self.steps_completed,
            "error": self.error,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "completeness_reports": self.completeness_reports,
            "blocked_at": self.blocked_at,
        }


# Global pipeline state
pipeline_state = PipelineState()


def _resolve_threshold() -> float:
    """Pick up the configured completeness threshold (default 0.8)."""
    return float(getattr(settings, "completeness_threshold", DEFAULT_COMPLETENESS_THRESHOLD))


def _gate(stage: str, artifact, *, db_name: str | None = None,
          snapshot_date: str | None = None, **context) -> CompletenessReport:
    """Run a completeness check on an upstream artifact and either record-and-pass
    or publish-and-abort.

    Raises ``CompletenessError`` when the upstream artifact fails the gate so the
    pipeline does *not* feed a degraded artifact into the next agent.
    """
    threshold = _resolve_threshold()
    report = check_completeness(stage, artifact, threshold=threshold,
                                snapshot_date=snapshot_date, **context)
    pipeline_state.completeness_reports.append(report.model_dump())
    # Publish a structured gate event to the agent-interaction transcript.
    log_gate(
        stage=stage,
        score=report.score,
        threshold=report.threshold,
        passed=report.passed,
        issues=report.issues,
        warnings=report.warnings,
        db_name=db_name,
        snapshot_date=snapshot_date,
    )
    if not report.passed:
        pipeline_state.blocked_at = stage
        # Publish a final, prominent message before bailing.
        logger.error(
            f"Pipeline halted: '{stage}' completeness {report.score:.2f} "
            f"< threshold {report.threshold:.2f}. Downstream agents will not run."
        )
        log_halt(
            blocked_at=stage,
            reason=f"completeness_score_{report.score:.2f}_below_{report.threshold:.2f}",
            db_name=db_name,
            snapshot_date=snapshot_date,
        )
        raise CompletenessError(report)
    return report


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

        log_handoff(
            sender="connection_agent",
            receiver="discovery_agent+profiling_agent",
            artifact="connection_ok",
            db_name=db_name,
            snapshot_date=snapshot_date,
            summary={"status": conn_result.get("status")},
        )

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

        # Hand-off: discovery -> dq_rules_generation (catalogue) and
        #           profiling -> classification (glossary). These two
        #           messages make the agent conversation explicit in the
        #           interaction log.
        log_handoff(
            sender="discovery_agent",
            receiver="dq_rules_agent",
            artifact="technical_catalogue",
            db_name=db_name,
            snapshot_date=snapshot_date,
            summary={
                "tables": catalogue.total_tables,
                "columns": catalogue.total_columns,
            },
        )
        log_handoff(
            sender="profiling_agent",
            receiver="classification_agent",
            artifact="data_glossary",
            db_name=db_name,
            snapshot_date=snapshot_date,
            summary={"entries": glossary.total_entries},
        )

        # Gate 1: discovery output must be complete before classification / DQ
        # rule generation rely on it.
        _gate(STAGE_DISCOVERY, catalogue, db_name=db_name, snapshot_date=snapshot_date)
        # Gate 2: profiling output must be complete before classification
        # consumes the glossary.
        _gate(STAGE_PROFILING, glossary, db_name=db_name, snapshot_date=snapshot_date,
              catalogue=catalogue)

        # Step 5: Classification
        pipeline_state.current_step = "classification"
        logger.info("Pipeline Step 5: Running classification")
        classification = run_classification(glossary, db_name=db_name, snapshot_date=snapshot_date)
        pipeline_state.steps_completed.append("classification")

        log_handoff(
            sender="classification_agent",
            receiver="dq_rules_agent",
            artifact="classification_report",
            db_name=db_name,
            snapshot_date=snapshot_date,
            summary={
                "total_columns": classification.total_columns,
                "cde_count": classification.cde_count,
                "cde_percentage": classification.cde_percentage,
            },
        )

        # Gate 3: classification must be complete before rule generation.
        _gate(STAGE_CLASSIFICATION, classification, db_name=db_name,
              snapshot_date=snapshot_date, glossary=glossary)

        # Step 6: DQ Rules Generation
        pipeline_state.current_step = "dq_rules_generation"
        logger.info("Pipeline Step 6: Generating DQ rules")
        rule_set = run_dq_rules_generation(
            catalogue, glossary, classification, db_name=db_name, snapshot_date=snapshot_date
        )
        pipeline_state.steps_completed.append("dq_rules_generation")

        log_handoff(
            sender="dq_rules_agent",
            receiver="dq_executor_agent",
            artifact="dq_rules",
            db_name=db_name,
            snapshot_date=snapshot_date,
            summary={
                "total_rules": rule_set.total_rules,
                "by_dimension": dict(rule_set.rules_by_dimension),
                "by_type": dict(rule_set.rules_by_type),
            },
        )

        # Gate 4: rule set must be complete before execution.
        _gate(
            STAGE_DQ_RULES,
            rule_set,
            db_name=db_name,
            snapshot_date=snapshot_date,
            catalogue=catalogue,
            classification=classification,
        )

        # Step 7: DQ Execution
        pipeline_state.current_step = "dq_execution"
        logger.info("Pipeline Step 7: Executing DQ rules")
        score_report = run_dq_execution(rule_set, db_name=db_name, snapshot_date=snapshot_date)
        pipeline_state.steps_completed.append("dq_execution")

        log_handoff(
            sender="dq_executor_agent",
            receiver="orchestrator",
            artifact="dq_scores",
            db_name=db_name,
            snapshot_date=snapshot_date,
            summary={
                "overall_score": score_report.overall_score,
                "rules_passed": score_report.rules_passed,
                "rules_failed": score_report.rules_failed,
            },
        )

        # Gate 5: final completeness check on the score report itself.
        _gate(STAGE_DQ_EXECUTION, score_report, db_name=db_name,
              snapshot_date=snapshot_date, rule_set=rule_set)

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
            "completeness_reports": pipeline_state.completeness_reports,
        }

    except CompletenessError as e:
        # An upstream artifact failed its completeness gate. The gate has
        # already published the issue list via the logger; mark the pipeline
        # failed but with a clear, structured reason and stop here.
        pipeline_state.status = PipelineStatus.FAILED
        pipeline_state.error = (
            f"completeness_check_failed:{e.report.stage} "
            f"score={e.report.score:.2f} threshold={e.report.threshold:.2f}"
        )
        pipeline_state.completed_at = datetime.now(timezone.utc).isoformat()
        return {
            "status": "halted",
            "reason": "completeness_check_failed",
            "blocked_at": e.report.stage,
            "completeness_reports": pipeline_state.completeness_reports,
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
