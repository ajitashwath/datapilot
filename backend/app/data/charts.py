import numpy as np
import pandas as pd

from app.data.engine import jsonable
from app.errors import UserError
from app.models import ChartSpec, TableResult

MAX_CATEGORIES = 60
MAX_PIE_SLICES = 12
MAX_SERIES = 8
MAX_POINTS = 2000


def to_numeric_column(df: pd.DataFrame, name: str) -> pd.Series:
    values = pd.to_numeric(df[name], errors="coerce")
    if values.notna().sum() == 0:
        raise UserError(f"Column '{name}' has no numeric values, so it cannot be plotted on a numeric axis.")
    return values


def edge_label(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 100 else f"{value:.3g}"


def histogram_data(values: np.ndarray, bins: int) -> list[dict]:
    counts, edges = np.histogram(values, bins=bins)
    return [
        {
            "bin": f"{edge_label(edges[i])} to {edge_label(edges[i + 1])}",
            "start": float(edges[i]),
            "end": float(edges[i + 1]),
            "count": int(counts[i]),
        }
        for i in range(len(counts))
    ]


def clipped_histogram(values: np.ndarray, bins: int) -> tuple[list[dict], int]:
    low, high = np.percentile(values, [1, 99])
    if high <= low:
        return histogram_data(values, bins), 0
    inside = values[(values >= low) & (values <= high)]
    return histogram_data(inside, bins), len(values) - len(inside)


def check_columns(df: pd.DataFrame, names: list[str]) -> None:
    missing = [n for n in names if n not in df.columns]
    if missing:
        raise UserError(f"The query result has no column named {missing}. Available columns: {list(df.columns)}.")


def build_chart(
    result: TableResult,
    chart_type: str,
    title: str,
    x: str,
    y: list[str],
    series: str | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    bins: int = 20,
) -> ChartSpec:
    if result.row_count == 0:
        raise UserError("The query returned no rows, so there is nothing to plot.")
    df = pd.DataFrame(result.rows, columns=result.columns)
    check_columns(df, [x] + y + ([series] if series else []))
    note = "Chart uses the first rows of the query result only." if result.truncated else None

    if chart_type == "histogram":
        values = to_numeric_column(df, x).dropna().to_numpy()
        data = histogram_data(values, max(2, min(bins, 50)))
        return ChartSpec(
            type="histogram", title=title, x_label=x_label or x, y_label=y_label or "Count",
            x_key="bin", y_keys=["count"], data=data, note=note,
        )

    if not y:
        raise UserError("At least one y column is required for this chart type.")

    if chart_type == "scatter":
        df = df.assign(**{x: to_numeric_column(df, x), y[0]: to_numeric_column(df, y[0])}).dropna(subset=[x, y[0]])
        if len(df) > MAX_POINTS:
            df = df.sample(MAX_POINTS, random_state=0)
            note = f"Showing a random sample of {MAX_POINTS} points."
        data = [{x: jsonable(a), y[0]: jsonable(b)} for a, b in zip(df[x], df[y[0]])]
        return ChartSpec(
            type="scatter", title=title, x_label=x_label or x, y_label=y_label or y[0],
            x_key=x, y_keys=[y[0]], data=data, note=note,
        )

    for name in y:
        df[name] = to_numeric_column(df, name)

    if chart_type == "pie":
        if len(df) > MAX_PIE_SLICES:
            raise UserError(f"A pie chart supports at most {MAX_PIE_SLICES} slices. Limit the query to the top categories.")
        df[x] = df[x].astype(str)
        return ChartSpec(
            type="pie", title=title, x_label=x_label or x, y_label=y_label or y[0],
            x_key=x, y_keys=[y[0]], data=[{x: a, y[0]: jsonable(b)} for a, b in zip(df[x], df[y[0]])], note=note,
        )

    limit = MAX_CATEGORIES if chart_type == "bar" else 500
    if series:
        if len(y) != 1:
            raise UserError("When a series column is used, provide exactly one y column.")
        wide = df.pivot_table(index=x, columns=series, values=y[0], aggfunc="sum", sort=False)
        if wide.shape[1] > MAX_SERIES:
            raise UserError(f"The series column has {wide.shape[1]} distinct values; limit it to at most {MAX_SERIES}.")
        wide.columns = [str(c) for c in wide.columns]
        wide = wide.reset_index()
        wide[x] = wide[x].astype(str)
        y_keys, frame = list(wide.columns[1:]), wide
    else:
        frame = df[[x] + y].copy()
        frame[x] = frame[x].astype(str)
        y_keys = y
    if len(frame) > limit:
        raise UserError(f"The result has {len(frame)} categories, too many for a {chart_type} chart (limit {limit}). Aggregate or limit it.")
    data = [{k: jsonable(v) for k, v in row.items()} for row in frame.to_dict("records")]
    return ChartSpec(
        type=chart_type, title=title, x_label=x_label or x, y_label=y_label or ", ".join(y_keys),
        x_key=x, y_keys=y_keys, data=data, note=note,
    )
