from typing import Optional

from pydantic import BaseModel


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    nullable: bool
    default_value: Optional[str] = None
    is_primary_key: bool = False
    is_unique: bool = False
    description: Optional[str] = None


class ForeignKey(BaseModel):
    column: str
    references_table: str
    references_column: str


class TableInfo(BaseModel):
    name: str
    row_count: int
    columns: list[ColumnInfo]
    primary_keys: list[str]
    foreign_keys: list[ForeignKey]
    description: Optional[str] = None


class TechnicalCatalogue(BaseModel):
    database_name: str
    tables: list[TableInfo]
    total_tables: int
    total_columns: int
    generated_at: str
