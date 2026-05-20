"""DQ Executor Agent - Executes DQ rules and produces scores."""

import logging
from datetime import datetime, timezone

from app.config.settings import settings
from app.models.dq_rules import (
    DimensionScore, DQRuleSet, DQScoreReport,
    RuleResult, TableScore,
)
from app.utils.db_utils import execute_dq_query, get_connection, get_row_count
from app.utils.llm_client import call_llm
from app.utils.prompts import DQ_INSIGHTS_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

DIMENSIONS = ["Accuracy", "Completeness", "Consistency", "Timeliness", "Validity", "Uniqueness"]


def run_dq_execution(rule_set: DQRuleSet | None = None, db_path: str | None = None) -> DQScoreReport:
    """
    Execute all DQ rules and produce consolidated scores.
    """
    # Load rules from file if not provided
    if rule_set is None:
        rules_path = settings.outputs_path / "dq_rules.json"
        if not rules_path.exists():
            raise FileNotFoundError("DQ rules not found. Run rule generation first.")
        rule_set = DQRuleSet.model_validate_json(rules_path.read_text())

    path = db_path or settings.database_path
    logger.info(f"Executing {rule_set.total_rules} DQ rules against {path}")

    conn = get_connection(path)
    try:
        rule_results = []
        for rule in rule_set.rules:
            result = _execute_rule(conn, rule)
            rule_results.append(result)

        # Calculate scores
        table_scores = _calculate_table_scores(rule_results)
        dimension_scores = _calculate_dimension_scores(rule_results)
        overall_score = _calculate_overall_score(dimension_scores)

        rules_passed = sum(1 for r in rule_results if r.passed)
        rules_failed = len(rule_results) - rules_passed

        report = DQScoreReport(
            database_name=path,
            overall_score=overall_score,
            table_scores=table_scores,
            dimension_scores=dimension_scores,
            rule_results=rule_results,
            total_rules=len(rule_results),
            rules_passed=rules_passed,
            rules_failed=rules_failed,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )

        # Save JSON output
        output_path = settings.outputs_path / "dq_scores.json"
        output_path.write_text(report.model_dump_json(indent=2))
        logger.info(f"DQ scores saved to {output_path}")

        # Generate markdown report with AI insights
        _generate_markdown_report(report)

        return report
    finally:
        conn.close()


def _execute_rule(conn, rule) -> RuleResult:
    """Execute a single DQ rule and return the result."""
    # Get total records for the table
    try:
        total_records = get_row_count(conn, rule.table_name)
    except Exception:
        total_records = 0

    # Execute the rule query (returns count of failures)
    query_result = execute_dq_query(conn, rule.sql_query)

    if query_result["status"] == "error":
        logger.warning(f"Rule {rule.rule_id} failed to execute: {query_result.get('message')}")
        failed_records = 0
        score = 0.0
    else:
        failed_records = query_result["result"] or 0
        if total_records > 0:
            score = round(((total_records - failed_records) / total_records) * 100, 2)
        else:
            score = 100.0

    # Clamp score between 0 and 100
    score = max(0.0, min(100.0, score))
    passed = (score / 100.0) >= rule.threshold

    return RuleResult(
        rule_id=rule.rule_id,
        rule_name=rule.rule_name,
        dimension=rule.dimension,
        table_name=rule.table_name,
        column_name=rule.column_name,
        total_records=total_records,
        failed_records=failed_records,
        score=score,
        passed=passed,
        threshold=rule.threshold,
        severity=rule.severity,
        cde_linked=rule.cde_linked,
    )


def _calculate_table_scores(rule_results: list[RuleResult]) -> list[TableScore]:
    """Calculate scores grouped by table."""
    tables = {}
    for r in rule_results:
        tables.setdefault(r.table_name, []).append(r)

    table_scores = []
    for table_name, results in tables.items():
        dim_scores = _calculate_dimension_scores(results)
        overall = sum(d.score for d in dim_scores) / len(dim_scores) if dim_scores else 0.0

        table_scores.append(TableScore(
            table_name=table_name,
            overall_score=round(overall, 2),
            dimension_scores=dim_scores,
            rules_count=len(results),
        ))

    return sorted(table_scores, key=lambda t: t.overall_score)


def _calculate_dimension_scores(rule_results: list[RuleResult]) -> list[DimensionScore]:
    """Calculate scores grouped by dimension."""
    dimensions = {}
    for r in rule_results:
        dimensions.setdefault(r.dimension, []).append(r)

    dim_scores = []
    for dim in DIMENSIONS:
        results = dimensions.get(dim, [])
        if results:
            # CDE-linked rules get 2x weight
            total_weight = 0
            weighted_sum = 0
            for r in results:
                weight = 2.0 if r.cde_linked else 1.0
                weighted_sum += r.score * weight
                total_weight += weight
            score = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0
            passed = sum(1 for r in results if r.passed)
            dim_scores.append(DimensionScore(
                dimension=dim,
                score=score,
                rules_count=len(results),
                rules_passed=passed,
                rules_failed=len(results) - passed,
            ))
        else:
            dim_scores.append(DimensionScore(
                dimension=dim,
                score=0.0,
                rules_count=0,
                rules_passed=0,
                rules_failed=0,
            ))

    return dim_scores


def _calculate_overall_score(dimension_scores: list[DimensionScore]) -> float:
    """Calculate overall database DQ score from dimension scores."""
    active_dims = [d for d in dimension_scores if d.rules_count > 0]
    if not active_dims:
        return 0.0
    return round(sum(d.score for d in active_dims) / len(active_dims), 2)


def _generate_markdown_report(report: DQScoreReport):
    """Generate a markdown report with AI-driven insights."""
    # Build summary for AI
    summary_lines = [
        f"Overall DQ Score: {report.overall_score}%",
        f"Total Rules: {report.total_rules} (Passed: {report.rules_passed}, Failed: {report.rules_failed})",
        "",
        "Dimension Scores:",
    ]
    for d in report.dimension_scores:
        summary_lines.append(f"  {d.dimension}: {d.score}% ({d.rules_passed}/{d.rules_count} passed)")

    summary_lines.append("\nTable Scores:")
    for t in report.table_scores:
        summary_lines.append(f"  {t.table_name}: {t.overall_score}%")

    summary_lines.append("\nFailed Rules:")
    for r in report.rule_results:
        if not r.passed:
            summary_lines.append(
                f"  [{r.severity}] {r.rule_name} ({r.dimension}): "
                f"{r.score}% (threshold: {r.threshold*100}%) - {r.table_name}.{r.column_name or '*'}"
            )

    # Generate AI insights
    try:
        insights = call_llm(
            DQ_INSIGHTS_SYSTEM_PROMPT,
            "\n".join(summary_lines),
            temperature=0.3,
        )
    except Exception as e:
        logger.warning(f"AI insights generation failed: {e}")
        insights = "AI insights unavailable."

    # Build markdown report
    md = f"""# Data Quality Report

**Generated:** {report.generated_at}  
**Database:** {report.database_name}

## Overall Score: {report.overall_score}%

| Metric | Value |
|--------|-------|
| Total Rules | {report.total_rules} |
| Rules Passed | {report.rules_passed} |
| Rules Failed | {report.rules_failed} |

## Dimension Scores

| Dimension | Score | Rules | Passed | Failed |
|-----------|-------|-------|--------|--------|
"""
    for d in report.dimension_scores:
        md += f"| {d.dimension} | {d.score}% | {d.rules_count} | {d.rules_passed} | {d.rules_failed} |\n"

    md += "\n## Table Scores\n\n| Table | Score | Rules |\n|-------|-------|-------|\n"
    for t in report.table_scores:
        md += f"| {t.table_name} | {t.overall_score}% | {t.rules_count} |\n"

    md += f"\n## AI Insights & Recommendations\n\n{insights}\n"

    md += "\n## Failed Rules Detail\n\n"
    for r in report.rule_results:
        if not r.passed:
            md += (
                f"### {r.rule_id}: {r.rule_name}\n"
                f"- **Dimension:** {r.dimension}\n"
                f"- **Table:** {r.table_name}\n"
                f"- **Column:** {r.column_name or 'N/A'}\n"
                f"- **Score:** {r.score}% (threshold: {r.threshold*100}%)\n"
                f"- **Severity:** {r.severity}\n"
                f"- **Failed Records:** {r.failed_records}/{r.total_records}\n\n"
            )

    # Save markdown report
    output_path = settings.outputs_path / "dq_report.md"
    output_path.write_text(md)
    logger.info(f"DQ report saved to {output_path}")
