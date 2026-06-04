"""Inter-agent completeness checks.

Each agent in the pipeline produces an artifact that is consumed by the next
agent. Before letting the pipeline proceed, we run a deterministic
completeness check on the upstream artifact: it scores how complete /
well-formed the artifact is on a 0..1 scale and lists concrete issues.

If the score falls below the configured threshold, the orchestrator
publishes the report and stops the pipeline rather than feeding a degraded
artifact into the next agent.

The checks here are intentionally rule-based (not LLM-based) so they are
fast, deterministic, and free.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.models.catalogue import TechnicalCatalogue
from app.models.classification import ClassificationReport
from app.models.dq_rules import DQRuleSet, DQScoreReport
from app.models.glossary import DataGlossary

logger = logging.getLogger(__name__)


# Stage names — keep in sync with orchestrator step labels.
STAGE_DISCOVERY = "discovery"
STAGE_PROFILING = "profiling"
STAGE_CLASSIFICATION = "classification"
STAGE_DQ_RULES = "dq_rules_generation"
STAGE_DQ_EXECUTION = "dq_execution"


class CompletenessReport(BaseModel):
    """Outcome of a completeness check on one upstream artifact."""

    stage: str
    score: float            # 0.0 .. 1.0
    threshold: float
    passed: bool
    issues: list[str] = []      # blocking deficiencies (each costs score)
    warnings: list[str] = []    # informational, do not affect pass/fail
    metrics: dict[str, Any] = {}
    checked_at: str

    def summary(self) -> str:
        head = (
            f"[completeness:{self.stage}] score={self.score:.2f} "
            f"threshold={self.threshold:.2f} passed={self.passed}"
        )
        if self.issues:
            head += " | issues: " + "; ".join(self.issues[:5])
            if len(self.issues) > 5:
                head += f" (+{len(self.issues) - 5} more)"
        return head


class CompletenessError(RuntimeError):
    """Raised when an upstream artifact fails its completeness check."""

    def __init__(self, report: CompletenessReport):
        self.report = report
        super().__init__(report.summary())


def _score_from_issues(num_issues: int, num_checks: int) -> float:
    """Score = (passed checks) / (total checks). Always in [0, 1]."""
    if num_checks <= 0:
        return 1.0
    passed = max(0, num_checks - num_issues)
    return round(passed / num_checks, 4)


def _check_discovery(catalogue: TechnicalCatalogue) -> tuple[list[str], list[str], dict, int]:
    issues: list[str] = []
    warnings: list[str] = []
    checks = 0

    checks += 1
    if not catalogue.tables:
        issues.append("catalogue has zero tables")

    checks += 1
    if catalogue.total_tables != len(catalogue.tables):
        issues.append(
            f"total_tables ({catalogue.total_tables}) does not match tables list "
            f"({len(catalogue.tables)})"
        )

    checks += 1
    actual_cols = sum(len(t.columns) for t in catalogue.tables)
    if catalogue.total_columns != actual_cols:
        issues.append(
            f"total_columns ({catalogue.total_columns}) does not match summed columns "
            f"({actual_cols})"
        )

    checks += 1
    empty_tables = [t.name for t in catalogue.tables if not t.columns]
    if empty_tables:
        issues.append(f"tables with no columns: {empty_tables[:5]}")

    checks += 1
    no_pk = [t.name for t in catalogue.tables if not t.primary_keys]
    if no_pk:
        warnings.append(f"tables without a primary key: {no_pk[:5]}")

    # FK targets must reference known tables.
    checks += 1
    table_names = {t.name for t in catalogue.tables}
    bad_fks: list[str] = []
    for t in catalogue.tables:
        for fk in t.foreign_keys:
            if fk.references_table not in table_names:
                bad_fks.append(f"{t.name}.{fk.column}->{fk.references_table}")
    if bad_fks:
        issues.append(f"foreign keys referencing unknown tables: {bad_fks[:5]}")

    # Description coverage is a quality signal but not blocking.
    total_cols = max(actual_cols, 1)
    described_cols = sum(
        1 for t in catalogue.tables for c in t.columns if (c.description or "").strip()
    )
    described_tables = sum(1 for t in catalogue.tables if (t.description or "").strip())
    coverage_col = described_cols / total_cols
    coverage_tbl = described_tables / max(len(catalogue.tables), 1)
    if coverage_col < 0.5:
        warnings.append(
            f"only {coverage_col:.0%} of columns have descriptions"
        )
    if coverage_tbl < 0.5:
        warnings.append(
            f"only {coverage_tbl:.0%} of tables have descriptions"
        )

    metrics = {
        "tables": len(catalogue.tables),
        "columns": actual_cols,
        "column_description_coverage": round(coverage_col, 4),
        "table_description_coverage": round(coverage_tbl, 4),
    }
    return issues, warnings, metrics, checks


def _check_profiling(
    glossary: DataGlossary,
    catalogue: TechnicalCatalogue | None,
) -> tuple[list[str], list[str], dict, int]:
    issues: list[str] = []
    warnings: list[str] = []
    checks = 0

    checks += 1
    if not glossary.entries:
        issues.append("glossary has zero entries")

    checks += 1
    if glossary.total_entries != len(glossary.entries):
        issues.append(
            f"total_entries ({glossary.total_entries}) does not match entries list "
            f"({len(glossary.entries)})"
        )

    # Every (table, column) in the catalogue must have a glossary entry.
    checks += 1
    if catalogue is not None:
        expected = {(t.name, c.name) for t in catalogue.tables for c in t.columns}
        actual = {(e.table_name, e.column_name) for e in glossary.entries}
        missing = expected - actual
        if missing:
            sample = list(missing)[:5]
            issues.append(
                f"{len(missing)} catalogue columns are missing glossary entries (e.g. {sample})"
            )

    # Profile must be populated (total_count is the most basic signal).
    checks += 1
    bad_profile = [
        f"{e.table_name}.{e.column_name}"
        for e in glossary.entries
        if e.profile is None or e.profile.total_count is None
    ]
    if bad_profile:
        issues.append(f"entries with empty profile: {bad_profile[:5]}")

    # Business descriptions: the agent has a fallback, so treat it as a warning.
    weak_desc = 0
    for e in glossary.entries:
        d = (e.business_description or "").strip()
        if not d or d.startswith(f"Column {e.column_name} in "):
            weak_desc += 1
    if glossary.entries:
        weak_ratio = weak_desc / len(glossary.entries)
        if weak_ratio > 0.3:
            warnings.append(
                f"{weak_ratio:.0%} of glossary entries have placeholder descriptions"
            )

    metrics = {
        "entries": len(glossary.entries),
        "weak_descriptions": weak_desc,
    }
    return issues, warnings, metrics, checks


def _check_classification(
    classification: ClassificationReport,
    glossary: DataGlossary | None,
) -> tuple[list[str], list[str], dict, int]:
    issues: list[str] = []
    warnings: list[str] = []
    checks = 0

    checks += 1
    if not classification.classifications:
        issues.append("classification report has zero entries")

    checks += 1
    if classification.total_columns != len(classification.classifications):
        issues.append(
            f"total_columns ({classification.total_columns}) does not match list "
            f"({len(classification.classifications)})"
        )

    # 1:1 coverage with glossary.
    checks += 1
    if glossary is not None:
        expected = {(e.table_name, e.column_name) for e in glossary.entries}
        actual = {(c.table_name, c.column_name) for c in classification.classifications}
        missing = expected - actual
        if missing:
            issues.append(
                f"{len(missing)} glossary columns are missing classifications (e.g. {list(missing)[:5]})"
            )

    # Labels must be in the allowed set.
    checks += 1
    allowed = {"Public", "Internal", "Confidential", "Restricted"}
    bad_labels = [
        f"{c.table_name}.{c.column_name}={c.classification}"
        for c in classification.classifications
        if c.classification not in allowed
    ]
    if bad_labels:
        issues.append(f"invalid classification labels: {bad_labels[:5]}")

    # We expect *some* CDEs to be flagged; otherwise downstream rules are weakened.
    checks += 1
    if classification.total_columns > 0 and classification.cde_count == 0:
        issues.append("no Critical Data Elements (CDE) were identified")

    # CDE rationale should accompany flagged CDEs (warning, not blocking).
    cde_missing_rationale = sum(
        1 for c in classification.classifications
        if c.is_cde and not (c.cde_rationale or "").strip()
    )
    if cde_missing_rationale:
        warnings.append(f"{cde_missing_rationale} CDEs have no rationale")

    metrics = {
        "total_columns": classification.total_columns,
        "cde_count": classification.cde_count,
        "cde_percentage": classification.cde_percentage,
    }
    return issues, warnings, metrics, checks


def _check_dq_rules(
    rule_set: DQRuleSet,
    catalogue: TechnicalCatalogue | None,
    classification: ClassificationReport | None,
    snapshot_date: str | None,
) -> tuple[list[str], list[str], dict, int]:
    issues: list[str] = []
    warnings: list[str] = []
    checks = 0

    checks += 1
    if not rule_set.rules:
        issues.append("rule set is empty")

    checks += 1
    if rule_set.total_rules != len(rule_set.rules):
        issues.append(
            f"total_rules ({rule_set.total_rules}) does not match rules list "
            f"({len(rule_set.rules)})"
        )

    # Each rule must have non-empty SQL.
    checks += 1
    no_sql = [r.rule_id for r in rule_set.rules if not (r.sql_query or "").strip()]
    if no_sql:
        issues.append(f"rules with empty SQL: {no_sql[:5]}")

    # Snapshot filter must be present when a snapshot_date was provided.
    checks += 1
    if snapshot_date:
        token = f"report_date = '{snapshot_date}'"
        missing_filter = [
            r.rule_id for r in rule_set.rules
            if token not in (r.sql_query or "")
        ]
        if missing_filter:
            issues.append(
                f"rules missing snapshot filter ({token}): {missing_filter[:5]}"
            )

    # Every table in the catalogue should have at least one rule.
    checks += 1
    if catalogue is not None:
        tables_with_rules = {r.table_name for r in rule_set.rules}
        missing_tables = [t.name for t in catalogue.tables if t.name not in tables_with_rules]
        if missing_tables:
            issues.append(f"tables with no rules: {missing_tables[:5]}")

    # Every CDE column should be covered by at least one rule.
    checks += 1
    if classification is not None:
        cde_cols = {
            (c.table_name, c.column_name)
            for c in classification.classifications if c.is_cde
        }
        covered = {
            (r.table_name, r.column_name)
            for r in rule_set.rules if r.column_name
        }
        uncovered = cde_cols - covered
        if uncovered:
            issues.append(
                f"{len(uncovered)} CDE columns have no rule (e.g. {list(uncovered)[:5]})"
            )

    # Dimension coverage (warning).
    expected_dims = {"Accuracy", "Completeness", "Consistency", "Validity", "Uniqueness"}
    present_dims = set(rule_set.rules_by_dimension.keys())
    missing_dims = expected_dims - present_dims
    if missing_dims:
        warnings.append(f"DQ dimensions not covered: {sorted(missing_dims)}")

    metrics = {
        "total_rules": len(rule_set.rules),
        "rules_by_dimension": dict(rule_set.rules_by_dimension),
        "rules_by_type": dict(rule_set.rules_by_type),
    }
    return issues, warnings, metrics, checks


def _check_dq_execution(
    report: DQScoreReport,
    rule_set: DQRuleSet | None,
) -> tuple[list[str], list[str], dict, int]:
    issues: list[str] = []
    warnings: list[str] = []
    checks = 0

    checks += 1
    if not report.rule_results:
        issues.append("no rules were executed")

    checks += 1
    if rule_set is not None and report.total_rules != rule_set.total_rules:
        issues.append(
            f"executed rule count ({report.total_rules}) does not match generated "
            f"rule set ({rule_set.total_rules})"
        )

    checks += 1
    if report.rules_passed + report.rules_failed != report.total_rules:
        issues.append(
            f"rules_passed + rules_failed ({report.rules_passed + report.rules_failed}) "
            f"does not equal total_rules ({report.total_rules})"
        )

    checks += 1
    if not report.table_scores:
        issues.append("table_scores is empty")

    checks += 1
    if not report.dimension_scores:
        issues.append("dimension_scores is empty")

    metrics = {
        "overall_score": report.overall_score,
        "rules_passed": report.rules_passed,
        "rules_failed": report.rules_failed,
    }
    return issues, warnings, metrics, checks


def check_completeness(
    stage: str,
    artifact: Any,
    *,
    threshold: float = 0.8,
    catalogue: TechnicalCatalogue | None = None,
    glossary: DataGlossary | None = None,
    classification: ClassificationReport | None = None,
    rule_set: DQRuleSet | None = None,
    snapshot_date: str | None = None,
) -> CompletenessReport:
    """Score the completeness of an upstream artifact for a given pipeline stage.

    Pass ``threshold`` (0..1) — anything below is considered a failed check.
    Optional kwargs let stage-specific checks compare the artifact against
    earlier artifacts (e.g. profiling vs. catalogue coverage).
    """
    if stage == STAGE_DISCOVERY:
        issues, warnings, metrics, checks = _check_discovery(artifact)
    elif stage == STAGE_PROFILING:
        issues, warnings, metrics, checks = _check_profiling(artifact, catalogue)
    elif stage == STAGE_CLASSIFICATION:
        issues, warnings, metrics, checks = _check_classification(artifact, glossary)
    elif stage == STAGE_DQ_RULES:
        issues, warnings, metrics, checks = _check_dq_rules(
            artifact, catalogue, classification, snapshot_date
        )
    elif stage == STAGE_DQ_EXECUTION:
        issues, warnings, metrics, checks = _check_dq_execution(artifact, rule_set)
    else:
        raise ValueError(f"Unknown completeness stage: {stage}")

    score = _score_from_issues(len(issues), checks)
    passed = score >= threshold and not any(
        # Hard fail if there are zero entries / zero rules etc.
        msg.startswith(("catalogue has zero", "glossary has zero",
                         "classification report has zero", "rule set is empty",
                         "no rules were executed"))
        for msg in issues
    )

    report = CompletenessReport(
        stage=stage,
        score=score,
        threshold=threshold,
        passed=passed,
        issues=issues,
        warnings=warnings,
        metrics=metrics,
        checked_at=datetime.now(timezone.utc).isoformat(),
    )

    # Publish: log at the appropriate level so the message surfaces in the
    # standard agent log files.
    if passed:
        logger.info(report.summary())
        for w in warnings:
            logger.warning(f"[completeness:{stage}] warning: {w}")
    else:
        logger.error(report.summary())
        for issue in issues:
            logger.error(f"[completeness:{stage}] issue: {issue}")

    return report
