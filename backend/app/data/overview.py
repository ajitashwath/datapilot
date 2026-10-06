import numpy as np

from app.data.charts import clipped_histogram
from app.data.datasets import DatasetStore
from app.data.profiler import is_identifier, quote
from app.models import ColumnProfile

MAX_ITEMS = 4


def measure_columns(store: DatasetStore, name: str) -> list[ColumnProfile]:
    profile = store.get_profile(name)
    measures = [c for c in profile.columns if c.kind == "numeric" and c.distinct > 1 and not is_identifier(c, profile.rows)]
    return sorted(measures, key=lambda c: abs((c.mean or 0) * (profile.rows - c.missing)), reverse=True)


def suggest_questions(store: DatasetStore, name: str) -> list[str]:
    profile = store.get_profile(name)
    measures = measure_columns(store, name)
    dimensions = sorted([c for c in profile.columns if c.kind == "categorical" and c.distinct >= 2], key=lambda c: c.distinct)
    dates = [c for c in profile.columns if c.kind == "date"]
    questions = []
    if measures and dimensions:
        measure, dim = measures[0].name, dimensions[0].name
        questions += [
            f"Which {dim} has the highest total {measure}?",
            f"Compare total {measure} across {dim} with a chart",
            f"What are the top 5 {dim} by {measure}?",
        ]
    if measures and dates:
        questions += [f"Show the monthly trend of {measures[0].name}", f"Which month had the highest total {measures[0].name}?"]
    if measures:
        questions += [f"Detect anomalies in {measures[0].name} and explain them", f"Show the distribution of {measures[0].name}"]
    questions.append("Are there any data quality problems in this dataset?")
    for rel in store.relationships:
        if name in (rel.left_table, rel.right_table):
            questions.append(f"Generate SQL that joins {rel.left_table} with {rel.right_table}")
            break
    return questions[:8]


def numeric_distribution(store: DatasetStore, table: str, column: str) -> dict:
    values = store.con.execute(
        f"SELECT {quote(column)} FROM {quote(table)} WHERE {quote(column)} IS NOT NULL"
    ).fetchnumpy()[column]
    bins, excluded = clipped_histogram(np.asarray(values, dtype=float), 12)
    return {"column": column, "bins": bins, "outliers_excluded": excluded}


def build_overview(store: DatasetStore, name: str) -> dict:
    profile = store.get_profile(name)
    quality = store.get_quality(name)
    measures = measure_columns(store, name)[:MAX_ITEMS]
    metrics = []
    for col in measures:
        total = store.con.execute(f"SELECT sum({quote(col.name)}) FROM {quote(name)}").fetchone()[0]
        metrics.append({"column": col.name, "sum": float(total), "mean": col.mean, "min": col.min, "max": col.max, "median": col.median})
    categories = []
    for col in [c for c in profile.columns if c.kind == "categorical"][:MAX_ITEMS]:
        non_null = profile.rows - col.missing
        categories.append({
            "column": col.name,
            "distinct": col.distinct,
            "top": [{"value": t.value, "count": t.count, "share_pct": round(t.count / non_null * 100, 1)} for t in col.top_values],
        })
    return {
        "dataset": name,
        "rows": profile.rows,
        "columns": profile.column_count,
        "duplicate_rows": profile.duplicate_rows,
        "quality_score": quality.score,
        "key_metrics": metrics,
        "missing": [
            {"column": c.name, "missing": c.missing, "missing_pct": c.missing_pct}
            for c in sorted(profile.columns, key=lambda c: c.missing, reverse=True) if c.missing
        ][:8],
        "distributions": [numeric_distribution(store, name, c.name) for c in measures],
        "categories": categories,
        "date_ranges": [{"column": c.name, "min": c.min, "max": c.max} for c in profile.columns if c.kind == "date"],
        "suggested_questions": suggest_questions(store, name),
    }
