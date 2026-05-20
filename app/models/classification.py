from pydantic import BaseModel


class ColumnClassification(BaseModel):
    table_name: str
    column_name: str
    classification: str  # Public, Internal, Confidential, Restricted
    is_cde: bool
    cde_rationale: str = ""
    classification_rationale: str = ""


class ClassificationReport(BaseModel):
    database_name: str
    classifications: list[ColumnClassification]
    total_columns: int
    cde_count: int
    cde_percentage: float
    classification_summary: dict[str, int]  # {Public: X, Internal: Y, ...}
    generated_at: str
