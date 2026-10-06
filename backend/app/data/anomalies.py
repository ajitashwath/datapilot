import duckdb
import numpy as np
import pandas as pd

from app.data.engine import jsonable
from app.data.profiler import quote
from app.errors import UserError
from app.models import AnomalyResult

MAX_AFFECTED_ROWS = 10


def fmt(value: float) -> str:
    return f"{value:,.2f}"


def load_values(con: duckdb.DuckDBPyConnection, table: str, column: str) -> pd.DataFrame:
    df = con.execute(
        f"SELECT rowid AS row_index, {quote(column)} AS value FROM {quote(table)} WHERE {quote(column)} IS NOT NULL"
    ).df()
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna()


def rows_for(con: duckdb.DuckDBPyConnection, table: str, flagged: pd.DataFrame, score_label: str) -> list[dict]:
    top = flagged.sort_values("score", ascending=False).head(MAX_AFFECTED_ROWS)
    ids = [int(i) for i in top["row_index"]]
    cursor = con.execute(f"SELECT rowid AS row_index, * FROM {quote(table)} WHERE rowid IN ({','.join(map(str, ids))})")
    names = [d[0] for d in cursor.description]
    by_id = {r[0]: dict(zip(names, [jsonable(v) for v in r])) for r in cursor.fetchall()}
    scores = dict(zip(top["row_index"].astype(int), top["score"]))
    result = []
    for row_id in ids:
        row = by_id.get(row_id, {"row_index": row_id})
        row[score_label] = round(float(scores[row_id]), 2)
        result.append(row)
    return result


def no_anomaly(method: str, column: str, reason: str, bounds: dict[str, float]) -> AnomalyResult:
    return AnomalyResult(
        is_anomaly=False, method=method, column=column, affected_rows=[], total_flagged=0,
        reason=reason, severity="none", bounds=bounds,
    )


def describe_direction(values: pd.Series, low: float, high: float) -> str:
    above, below = int((values > high).sum()), int((values < low).sum())
    parts = []
    if above:
        parts.append(f"{above} above the upper boundary")
    if below:
        parts.append(f"{below} below the lower boundary")
    return " and ".join(parts)


def detect_iqr(con: duckdb.DuckDBPyConnection, table: str, column: str, multiplier: float = 1.5) -> AnomalyResult:
    df = load_values(con, table, column)
    if len(df) < 4:
        raise UserError(f"'{column}' has too few numeric values for IQR detection.")
    q1, q3 = np.percentile(df["value"], [25, 75])
    iqr = q3 - q1
    low, high = q1 - multiplier * iqr, q3 + multiplier * iqr
    bounds = {"q1": float(q1), "q3": float(q3), "iqr": float(iqr), "lower": float(low), "upper": float(high)}
    if iqr == 0:
        return no_anomaly("IQR", column, f"'{column}' has no spread between Q1 and Q3 ({fmt(q1)}), so IQR fences are not informative.", bounds)
    df["score"] = np.where(
        df["value"] > high, (df["value"] - high) / iqr, np.where(df["value"] < low, (low - df["value"]) / iqr, 0.0)
    )
    flagged = df[df["score"] > 0]
    if flagged.empty:
        return no_anomaly("IQR", column, f"All {len(df)} values of '{column}' are inside the IQR fences {fmt(low)} to {fmt(high)}.", bounds)
    worst = flagged["score"].max()
    severity = "high" if worst >= 3 else "medium" if worst >= 1 else "low"
    extreme = flagged.loc[flagged["score"].idxmax(), "value"]
    reason = (
        f"{len(flagged)} of {len(df)} values in '{column}' fall outside the IQR fences "
        f"[{fmt(low)}, {fmt(high)}] ({describe_direction(flagged['value'], low, high)}). "
        f"Q1={fmt(q1)}, Q3={fmt(q3)}, IQR={fmt(iqr)}. The most extreme value is {fmt(extreme)}, "
        f"{worst:.1f} IQRs beyond the nearest fence."
    )
    return AnomalyResult(
        is_anomaly=True, method="IQR", column=column, affected_rows=rows_for(con, table, flagged, "iqr_distance"),
        total_flagged=len(flagged), reason=reason, severity=severity, bounds=bounds,
    )


def detect_zscore(con: duckdb.DuckDBPyConnection, table: str, column: str, threshold: float = 3.0) -> AnomalyResult:
    df = load_values(con, table, column)
    if len(df) < 4:
        raise UserError(f"'{column}' has too few numeric values for z-score detection.")
    mean, std = float(df["value"].mean()), float(df["value"].std())
    low, high = mean - threshold * std, mean + threshold * std
    bounds = {"mean": mean, "std": std, "lower": low, "upper": high}
    if std == 0:
        return no_anomaly("Z-score", column, f"'{column}' is constant, so z-scores are undefined.", bounds)
    df["score"] = ((df["value"] - mean) / std).abs()
    flagged = df[df["score"] > threshold]
    if flagged.empty:
        return no_anomaly(
            "Z-score", column, f"No value of '{column}' is more than {threshold:g} standard deviations from the mean {fmt(mean)}.", bounds
        )
    worst = flagged["score"].max()
    severity = "high" if worst >= 5 else "medium" if worst >= 4 else "low"
    reason = (
        f"{len(flagged)} of {len(df)} values in '{column}' are more than {threshold:g} standard deviations "
        f"from the mean ({describe_direction(flagged['value'], low, high)}). Mean={fmt(mean)}, std={fmt(std)}, "
        f"allowed range [{fmt(low)}, {fmt(high)}]. The largest |z| is {worst:.1f}."
    )
    return AnomalyResult(
        is_anomaly=True, method="Z-score", column=column, affected_rows=rows_for(con, table, flagged, "z_score"),
        total_flagged=len(flagged), reason=reason, severity=severity, bounds=bounds,
    )


def choose_granularity(days: int) -> str:
    if days <= 120:
        return "day"
    return "week" if days <= 900 else "month"


def detect_timeseries(
    con: duckdb.DuckDBPyConnection, table: str, column: str, date_column: str, agg: str = "sum", threshold: float = 3.5
) -> AnomalyResult:
    if agg not in ("sum", "mean", "count"):
        raise UserError("agg must be one of sum, mean, count.")
    dates = f"TRY_CAST({quote(date_column)} AS DATE)"
    span = con.execute(f"SELECT date_diff('day', min({dates}), max({dates})) FROM {quote(table)}").fetchone()[0]
    if span is None:
        raise UserError(f"'{date_column}' could not be read as dates.")
    grain = choose_granularity(span)
    expr = {"sum": f"sum({quote(column)})", "mean": f"avg({quote(column)})", "count": "count(*)"}[agg]
    series = con.execute(
        f"SELECT CAST(date_trunc('{grain}', {dates}) AS DATE) AS period, {expr} AS value "
        f"FROM {quote(table)} WHERE {dates} IS NOT NULL GROUP BY 1 ORDER BY 1"
    ).df()
    series["value"] = pd.to_numeric(series["value"], errors="coerce")
    series["period"] = pd.to_datetime(series["period"]).dt.strftime("%Y-%m-%d")
    series = series.dropna().reset_index(drop=True)
    if grain != "day" and len(series) > 10:
        series = series.iloc[1:-1].reset_index(drop=True)
    if len(series) < 8:
        raise UserError(f"Only {len(series)} time periods are available, which is too few for time series anomaly detection.")
    window = max(3, min(7, (len(series) // 2) | 1))
    expected = series["value"].rolling(window, center=True, min_periods=3).median()
    residual = series["value"] - expected
    scale = 1.4826 * float((residual - residual.median()).abs().median())
    if scale == 0:
        scale = float(residual.std()) or 1.0
    series["expected"] = expected
    series["score"] = (residual / scale).abs()
    flagged = series[series["score"] > threshold]
    label = f"{agg} of '{column}' per {grain}" if agg != "count" else f"row count per {grain}"
    method = "Rolling median (time series)"
    bounds = {"robust_scale": scale, "window_periods": float(window)}
    if flagged.empty:
        return no_anomaly(
            method, column, f"No {grain} deviates from its rolling median by more than {threshold:g} robust deviations ({label}).", bounds
        )
    worst = flagged["score"].max()
    severity = "high" if worst >= 8 else "medium" if worst >= 5 else "low"
    top = flagged.sort_values("score", ascending=False).head(MAX_AFFECTED_ROWS)
    rows = [
        {
            "period": str(r.period),
            "value": round(float(r.value), 2),
            "expected": round(float(r.expected), 2),
            "deviation_pct": round((r.value - r.expected) / r.expected * 100, 1) if r.expected else None,
            "robust_score": round(float(r.score), 2),
        }
        for r in top.itertuples()
    ]
    best = top.iloc[0]
    reason = (
        f"{len(flagged)} of {len(series)} periods deviate from the {window}-period rolling median by more than "
        f"{threshold:g} robust deviations ({label}; the first and last {grain} are excluded because they may be partial). The largest is {best.period}: {fmt(best.value)} against an expected {fmt(best.expected)}."
    )
    return AnomalyResult(
        is_anomaly=True, method=method, column=column, affected_rows=rows,
        total_flagged=len(flagged), reason=reason, severity=severity, bounds=bounds,
    )
