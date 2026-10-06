import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.agent.llm import ToolSpec
from app.data.anomalies import detect_iqr, detect_timeseries, detect_zscore
from app.data.charts import build_chart
from app.data.overview import build_overview, measure_columns
from app.data.relations import infer_between
from app.data.sandbox import run_python
from app.errors import UserError
from app.logging_setup import log_event
from app.models import AnomalyResult, TableResult, ToolResult
from app.session import Session

MAX_CHART_ROWS = 20000
LLM_ROWS = 30
LLM_CHARS = 9000
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}


class InspectDatasetArgs(BaseModel):
    dataset: str = Field(description="Table name of the dataset.")
    sample_rows: int = Field(5, ge=1, le=20, description="Number of sample rows to return.")


class GetSchemaArgs(BaseModel):
    pass


class ColumnStatisticsArgs(BaseModel):
    dataset: str
    column: str


class ExecuteSqlArgs(BaseModel):
    query: str = Field(description="A single read-only DuckDB SELECT statement. Quote identifiers with double quotes.")


class ExecutePythonArgs(BaseModel):
    code: str = Field(description="Python using pandas (pd) and numpy (np). Each dataset is a DataFrame named after its table. Assign the final answer to a variable named result.")
    datasets: list[str] = Field(default_factory=list, description="Dataset names to load. Empty means all datasets.")


class VisualizationArgs(BaseModel):
    chart_type: Literal["bar", "line", "pie", "scatter", "histogram"]
    sql: str = Field(description="DuckDB SELECT whose result provides the chart data. Aggregate in SQL and ORDER BY the x axis for line charts.")
    x: str = Field(description="Result column for the x axis (the numeric column for histograms, the category column for pie charts).")
    y: list[str] = Field(default_factory=list, description="Result column(s) for the y axis or slice values. Not needed for histograms.")
    series: str | None = Field(None, description="Optional result column that splits bar or line charts into several series. Use with exactly one y column.")
    title: str
    x_label: str | None = None
    y_label: str | None = None
    bins: int = Field(20, ge=2, le=50, description="Histogram bin count.")


class DetectAnomaliesArgs(BaseModel):
    dataset: str
    column: str | None = Field(None, description="Numeric column to check. Omit to scan all numeric measure columns.")
    method: Literal["iqr", "zscore", "timeseries"] = "iqr"
    date_column: str | None = Field(None, description="Date column, used by the timeseries method. Defaults to the first date column.")
    agg: Literal["sum", "mean", "count"] = Field("sum", description="How to aggregate values per period for the timeseries method.")
    threshold: float | None = Field(None, gt=0, description="Override the default sensitivity (IQR multiplier, z-score cutoff or robust score cutoff).")


class DatasetArgs(BaseModel):
    dataset: str


class CompareDatasetsArgs(BaseModel):
    left: str
    right: str


class SetFiltersArgs(BaseModel):
    filters: dict[str, str] = Field(description="Entities or filters the user is focusing on, for example {'region': 'North America'}.")
    replace: bool = Field(False, description="True replaces all stored filters, false merges. An empty dict with replace=true clears them.")


@dataclass
class ToolDef:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[[Session, Any], ToolResult]


def table_payload(table: TableResult) -> dict:
    return table.model_dump(mode="json")


def inspect_dataset(session: Session, args: InspectDatasetArgs) -> ToolResult:
    profile = session.store.get_profile(args.dataset)
    sample = session.store.query(f'SELECT * FROM "{args.dataset}" LIMIT {args.sample_rows}')
    columns = [
        {"name": c.name, "dtype": c.dtype, "kind": c.kind, "missing_pct": c.missing_pct, "distinct": c.distinct, "min": c.min, "max": c.max}
        for c in profile.columns
    ]
    data = {"dataset": args.dataset, "rows": profile.rows, "duplicate_rows": profile.duplicate_rows, "columns": columns, "sample": table_payload(sample)}
    return ToolResult(data=data, table=sample)


def get_schema(session: Session, args: GetSchemaArgs) -> ToolResult:
    datasets = {
        name: {"rows": p.rows, "columns": [{"name": c.name, "dtype": c.dtype, "kind": c.kind} for c in p.columns]}
        for name, p in session.store.profiles.items()
    }
    relationships = [r.model_dump(mode="json") for r in session.store.relationships]
    return ToolResult(data={"datasets": datasets, "relationships": relationships})


def get_column_statistics(session: Session, args: ColumnStatisticsArgs) -> ToolResult:
    column = session.store.get_column(args.dataset, args.column)
    return ToolResult(data=column.model_dump(mode="json"))


def execute_sql(session: Session, args: ExecuteSqlArgs) -> ToolResult:
    table = session.store.query(args.query)
    return ToolResult(data=table_payload(table), sql=args.query.strip().rstrip(";"), table=table)


def execute_python(session: Session, args: ExecutePythonArgs) -> ToolResult:
    names = args.datasets or sorted(session.store.table_names())
    paths = {name: session.store.parquet_path(name) for name in names}
    settings = session.store.settings
    output = run_python(args.code, paths, settings.python_timeout_seconds, settings.python_memory_mb, settings.max_result_rows)
    if not output["ok"]:
        return ToolResult(ok=False, error=output["error"], code=args.code, data={"stdout": output["stdout"]})
    result = output["result"]
    table = None
    data: dict = {"stdout": output["stdout"]}
    if result["kind"] == "table":
        table = TableResult(columns=result["columns"], rows=result["rows"], row_count=result["row_count"], truncated=result["truncated"])
        data.update(table_payload(table))
    else:
        data["value"] = result["value"]
    return ToolResult(data=data, code=args.code, table=table)


def create_visualization(session: Session, args: VisualizationArgs) -> ToolResult:
    table = session.store.query(args.sql, max_rows=MAX_CHART_ROWS)
    chart = build_chart(table, args.chart_type, args.title, args.x, args.y, args.series, args.x_label, args.y_label, args.bins)
    data = {"chart_type": chart.type, "title": chart.title, "points": len(chart.data), "series": chart.y_keys, "preview": chart.data[:15]}
    return ToolResult(data=data, sql=args.sql.strip().rstrip(";"), chart=chart)


def run_detection(session: Session, args: DetectAnomaliesArgs, column: str, date_column: str | None) -> AnomalyResult:
    con, table = session.store.con, args.dataset
    if args.method == "zscore":
        return detect_zscore(con, table, column, args.threshold or 3.0)
    if args.method == "timeseries":
        if not date_column:
            raise UserError("The timeseries method needs a date column and this dataset has none.")
        return detect_timeseries(con, table, column, date_column, args.agg, args.threshold or 3.5)
    return detect_iqr(con, table, column, args.threshold or 1.5)


def detect_anomalies(session: Session, args: DetectAnomaliesArgs) -> ToolResult:
    profile = session.store.get_profile(args.dataset)
    date_column = args.date_column
    if date_column:
        session.store.get_column(args.dataset, date_column)
    else:
        date_column = next((c.name for c in profile.columns if c.kind == "date"), None)
    if args.column:
        column = session.store.get_column(args.dataset, args.column)
        if column.kind != "numeric":
            raise UserError(f"Column '{args.column}' is {column.kind}, anomaly detection needs a numeric column.")
        columns = [args.column]
    else:
        columns = [c.name for c in measure_columns(session.store, args.dataset)][:8]
        if not columns:
            raise UserError("This dataset has no numeric measure columns to scan.")
    results = []
    for name in columns:
        try:
            results.append(run_detection(session, args, name, date_column))
        except UserError:
            if args.column:
                raise
    flagged = sorted([r for r in results if r.is_anomaly], key=lambda r: SEVERITY_ORDER[r.severity])
    shown = flagged if (flagged or not args.column) else results
    data = {
        "scanned_columns": columns,
        "any_anomaly": bool(flagged),
        "results": [r.model_dump(mode="json") for r in shown],
    }
    return ToolResult(data=data, anomalies=shown)


def data_quality_check(session: Session, args: DatasetArgs) -> ToolResult:
    return ToolResult(data=session.store.get_quality(args.dataset).model_dump(mode="json"))


def compare_datasets(session: Session, args: CompareDatasetsArgs) -> ToolResult:
    left, right = session.store.get_profile(args.left), session.store.get_profile(args.right)
    right_types = {c.name: c.dtype for c in right.columns}
    shared = [{"column": c.name, "left_type": c.dtype, "right_type": right_types[c.name]} for c in left.columns if c.name in right_types]
    relationships = session.store.relationships_between(args.left, args.right)
    if not relationships:
        relationships = infer_between(session.store.con, left, right)
    data = {
        "left": {"dataset": left.name, "rows": left.rows},
        "right": {"dataset": right.name, "rows": right.rows},
        "shared_columns": shared,
        "join_candidates": [{**r.model_dump(mode="json"), "join_sql": r.join_sql()} for r in relationships],
        "join_advice": "Aggregate the many side before joining to avoid double counting." if relationships else "No reliable join key was found.",
    }
    return ToolResult(data=data)


def generate_summary(session: Session, args: DatasetArgs) -> ToolResult:
    return ToolResult(data=build_overview(session.store, args.dataset))


def set_context_filters(session: Session, args: SetFiltersArgs) -> ToolResult:
    if args.replace:
        session.filters = {}
    session.filters.update(args.filters)
    return ToolResult(data={"filters": dict(session.filters)})


TOOLS = [
    ToolDef("inspect_dataset", "Return row count, column types, ranges and sample rows of one dataset. Use first to learn what the data looks like.", InspectDatasetArgs, inspect_dataset),
    ToolDef("get_schema", "List every dataset with its columns, types and the inferred or user-declared relationships between datasets.", GetSchemaArgs, get_schema),
    ToolDef("get_column_statistics", "Return exact statistics for one column (missing count, distinct count, min, max, mean, median, quartiles, top values).", ColumnStatisticsArgs, get_column_statistics),
    ToolDef("execute_sql", "Run one read-only DuckDB SELECT over the uploaded datasets and return the rows. Use for aggregations, rankings, filters and joins. All numbers in answers must come from here or other tools.", ExecuteSqlArgs, execute_sql),
    ToolDef("execute_python", "Run sandboxed pandas/numpy code when SQL is not enough (for example correlations or custom statistics). Assign the answer to result.", ExecutePythonArgs, execute_python),
    ToolDef("create_visualization", "Draw a bar, line, pie, scatter or histogram chart. The chart values come from the SQL you provide, never from your own numbers.", VisualizationArgs, create_visualization),
    ToolDef("detect_anomalies", "Run statistical anomaly detection (IQR, z-score or time series rolling median) and return the flagged rows with a computed explanation.", DetectAnomaliesArgs, detect_anomalies),
    ToolDef("data_quality_check", "Report missing values, duplicates, invalid types, suspicious values, constant and high-cardinality columns, date parsing problems.", DatasetArgs, data_quality_check),
    ToolDef("compare_datasets", "Compare two datasets: shared columns, candidate join keys with overlap and cardinality, and a ready join SQL.", CompareDatasetsArgs, compare_datasets),
    ToolDef("generate_summary", "Produce an overview of a dataset: key metrics, distributions, category breakdowns, missing data and suggested questions.", DatasetArgs, generate_summary),
    ToolDef("set_context_filters", "Remember entities or filters the user is focusing on so later questions like 'its trend' can be resolved. Call it whenever the user settles on a specific entity.", SetFiltersArgs, set_context_filters),
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}


def tool_specs() -> list[ToolSpec]:
    specs = []
    for tool in TOOLS:
        schema = tool.args_model.model_json_schema()
        schema.pop("title", None)
        specs.append(ToolSpec(name=tool.name, description=tool.description, input_schema=schema))
    return specs


def run_tool(session: Session, name: str, raw_input: Any) -> ToolResult:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        return ToolResult(ok=False, error=f"Unknown tool '{name}'. Available tools: {', '.join(TOOLS_BY_NAME)}.")
    started = time.perf_counter()
    try:
        args = tool.args_model.model_validate(raw_input if isinstance(raw_input, dict) else {})
        result = tool.handler(session, args)
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
        result = ToolResult(ok=False, error=f"Invalid arguments for {name}: {problems}")
    except UserError as exc:
        result = ToolResult(ok=False, error=exc.message)
    except Exception:
        log_event("tool_exception", tool=name, exc_info=True)
        result = ToolResult(ok=False, error="The tool failed unexpectedly. Try a simpler approach.")
    log_event(
        "tool_call", tool=name, ok=result.ok, error=result.error,
        duration_ms=round((time.perf_counter() - started) * 1000, 1), args=json.dumps(raw_input, default=str)[:300],
    )
    return result


def trim_for_llm(value: Any) -> Any:
    if isinstance(value, list):
        trimmed = [trim_for_llm(v) for v in value[:LLM_ROWS]]
        if len(value) > LLM_ROWS:
            trimmed.append(f"... {len(value) - LLM_ROWS} more items omitted")
        return trimmed
    if isinstance(value, dict):
        return {k: trim_for_llm(v) for k, v in value.items()}
    return value


def result_for_llm(result: ToolResult) -> str:
    payload: dict = {"ok": result.ok}
    if result.error:
        payload["error"] = result.error
    if result.data:
        payload["data"] = trim_for_llm(result.data)
    text = json.dumps(payload, default=str)
    return text if len(text) <= LLM_CHARS else text[:LLM_CHARS] + "... [truncated]"
