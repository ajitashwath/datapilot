from typing import Any, Literal

from pydantic import BaseModel, Field

ColumnKind = Literal["numeric", "categorical", "date", "text", "boolean"]


class TopValue(BaseModel):
    value: Any
    count: int


class ColumnProfile(BaseModel):
    name: str
    dtype: str
    kind: ColumnKind
    missing: int
    missing_pct: float
    distinct: int
    min: Any = None
    max: Any = None
    mean: float | None = None
    std: float | None = None
    median: float | None = None
    q1: float | None = None
    q3: float | None = None
    top_values: list[TopValue] = []
    samples: list[Any] = []


class DatasetProfile(BaseModel):
    name: str
    filename: str
    rows: int
    column_count: int
    duplicate_rows: int
    skipped_rows: int = 0
    columns: list[ColumnProfile]


class QualityIssue(BaseModel):
    severity: Literal["low", "medium", "high"]
    type: str
    column: str | None = None
    message: str
    count: int = 0


class QualityReport(BaseModel):
    dataset: str
    score: int
    issues: list[QualityIssue]


class TableResult(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool = False


class AnomalyResult(BaseModel):
    is_anomaly: bool
    method: str
    column: str
    affected_rows: list[dict[str, Any]]
    total_flagged: int
    reason: str
    severity: Literal["none", "low", "medium", "high"]
    bounds: dict[str, float] = {}


class ChartSpec(BaseModel):
    type: Literal["bar", "line", "pie", "scatter", "histogram"]
    title: str
    x_label: str
    y_label: str
    x_key: str
    y_keys: list[str]
    data: list[dict[str, Any]]
    note: str | None = None


class Relationship(BaseModel):
    left_table: str
    left_column: str
    right_table: str
    right_column: str
    cardinality: Literal["one-to-one", "one-to-many", "many-to-one", "many-to-many"]
    overlap_pct: float
    source: Literal["inferred", "user"] = "inferred"

    def join_sql(self) -> str:
        return (
            f'SELECT * FROM "{self.left_table}" l JOIN "{self.right_table}" r '
            f'ON l."{self.left_column}" = r."{self.right_column}"'
        )


class ToolResult(BaseModel):
    ok: bool = True
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    sql: str | None = None
    code: str | None = None
    table: TableResult | None = None
    chart: ChartSpec | None = None
    anomalies: list[AnomalyResult] = []
