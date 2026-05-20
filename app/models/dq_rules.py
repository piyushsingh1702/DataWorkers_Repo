from typing import Optional

from pydantic import BaseModel


class DQRule(BaseModel):
    rule_id: str
    rule_name: str
    dimension: str  # Accuracy, Completeness, Consistency, Timeliness, Validity, Uniqueness
    table_name: str
    column_name: Optional[str] = None
    rule_type: str  # technical or business
    description: str
    sql_query: str
    threshold: float = 0.95
    severity: str = "medium"  # low, medium, high, critical
    cde_linked: bool = False


class DQRuleSet(BaseModel):
    database_name: str
    rules: list[DQRule]
    total_rules: int
    rules_by_dimension: dict[str, int]
    rules_by_type: dict[str, int]
    generated_at: str


class RuleResult(BaseModel):
    rule_id: str
    rule_name: str
    dimension: str
    table_name: str
    column_name: Optional[str] = None
    total_records: int
    failed_records: int
    score: float  # 0-100
    passed: bool
    threshold: float
    severity: str
    cde_linked: bool


class DimensionScore(BaseModel):
    dimension: str
    score: float
    rules_count: int
    rules_passed: int
    rules_failed: int


class TableScore(BaseModel):
    table_name: str
    overall_score: float
    dimension_scores: list[DimensionScore]
    rules_count: int


class DQScoreReport(BaseModel):
    database_name: str
    overall_score: float
    table_scores: list[TableScore]
    dimension_scores: list[DimensionScore]
    rule_results: list[RuleResult]
    total_rules: int
    rules_passed: int
    rules_failed: int
    generated_at: str
