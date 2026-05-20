from typing import Optional

from pydantic import BaseModel


class ColumnProfile(BaseModel):
    table_name: str
    column_name: str
    data_type: str
    total_count: int
    null_count: int
    null_percentage: float
    distinct_count: int
    # Numeric stats
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    median_value: Optional[float] = None
    std_dev: Optional[float] = None
    # String stats
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    avg_length: Optional[float] = None
    # Sample values
    sample_values: list[str] = []
    top_values: list[dict] = []


class GlossaryEntry(BaseModel):
    table_name: str
    column_name: str
    business_description: str
    data_domain: str
    is_enumeration: bool = False
    enum_values: list[str] = []
    is_pii: bool = False
    profile: ColumnProfile


class DataGlossary(BaseModel):
    database_name: str
    entries: list[GlossaryEntry]
    total_entries: int
    generated_at: str
