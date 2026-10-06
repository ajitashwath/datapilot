import numpy as np
import pandas as pd
import pytest

from app.agent.tools import run_tool
from app.data.anomalies import detect_iqr, detect_timeseries, detect_zscore
from app.errors import UserError


def load_frame(store, name: str, frame: pd.DataFrame) -> None:
    path = store.directory / f"{name}.csv"
    store.directory.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)
    store.add_csv(f"{name}.csv", path.read_bytes())


@pytest.fixture
def synthetic(empty_store):
    rng = np.random.default_rng(0)
    values = rng.normal(100, 5, size=300).round(2)
    values[10], values[200] = 400.0, -150.0
    days = pd.date_range("2024-01-01", periods=300).strftime("%Y-%m-%d")
    load_frame(empty_store, "series", pd.DataFrame({"day": days, "value": values, "flat": 7}))
    return empty_store


def test_iqr_flags_planted_outliers_with_explanation(synthetic):
    result = detect_iqr(synthetic.con, "series", "value")
    flagged = {row["row_index"] for row in result.affected_rows}
    assert {10, 200} <= flagged
    assert result.is_anomaly and result.method == "IQR" and result.severity == "high"
    assert f"{result.bounds['upper']:,.2f}" in result.reason
    assert result.bounds["lower"] < 100 < result.bounds["upper"]


def test_iqr_matches_numpy(synthetic):
    frame = synthetic.con.execute("SELECT value FROM series").df()
    q1, q3 = np.percentile(frame["value"], [25, 75])
    result = detect_iqr(synthetic.con, "series", "value")
    assert result.bounds["upper"] == pytest.approx(q3 + 1.5 * (q3 - q1))
    outside = ((frame["value"] > result.bounds["upper"]) | (frame["value"] < result.bounds["lower"])).sum()
    assert result.total_flagged == outside


def test_zscore_flags_extremes(synthetic):
    result = detect_zscore(synthetic.con, "series", "value")
    assert {10, 200} <= {row["row_index"] for row in result.affected_rows}
    assert "standard deviations" in result.reason


def test_constant_column_reports_no_anomaly(synthetic):
    result = detect_iqr(synthetic.con, "series", "flat")
    assert not result.is_anomaly and result.severity == "none"


def test_clean_data_reports_no_anomaly(empty_store):
    load_frame(empty_store, "clean", pd.DataFrame({"v": np.linspace(1, 100, 100)}))
    assert not detect_iqr(empty_store.con, "clean", "v").is_anomaly
    assert not detect_zscore(empty_store.con, "clean", "v").is_anomaly


def test_timeseries_detects_spike(empty_store):
    days = pd.date_range("2024-01-01", periods=90)
    values = 50 + np.sin(np.arange(90) / 5) * 5
    values[45] = 400
    load_frame(empty_store, "ts", pd.DataFrame({"day": days.strftime("%Y-%m-%d"), "v": values}))
    result = detect_timeseries(empty_store.con, "ts", "v", "day")
    assert result.is_anomaly
    assert result.affected_rows[0]["period"] == days[45].strftime("%Y-%m-%d")
    assert "rolling median" in result.reason


def test_timeseries_needs_enough_periods(empty_store):
    load_frame(empty_store, "tiny", pd.DataFrame({"day": ["2024-01-01", "2024-01-02", "2024-01-03"], "v": [1, 2, 3]}))
    with pytest.raises(UserError):
        detect_timeseries(empty_store.con, "tiny", "v", "day")


def test_too_few_values(empty_store):
    load_frame(empty_store, "few", pd.DataFrame({"v": [1, 2]}))
    with pytest.raises(UserError):
        detect_iqr(empty_store.con, "few", "v")


def test_sample_data_contains_planted_revenue_anomalies(session):
    result = run_tool(session, "detect_anomalies", {"dataset": "orders", "column": "revenue"})
    assert result.ok and result.anomalies[0].is_anomaly
    revenues = [row["revenue"] for row in result.anomalies[0].affected_rows]
    assert 187500.0 in revenues or max(revenues) > 100000


def test_sample_data_order_spike_found_by_timeseries(session):
    result = run_tool(session, "detect_anomalies", {"dataset": "orders", "method": "timeseries", "column": "revenue", "agg": "count"})
    periods = [row["period"] for row in result.anomalies[0].affected_rows]
    assert any(p.startswith("2024-03") for p in periods)


def test_scan_skips_identifier_columns(session):
    result = run_tool(session, "detect_anomalies", {"dataset": "orders"})
    assert "order_id" not in result.data["scanned_columns"]
    assert result.data["any_anomaly"]


def test_categorical_column_is_rejected(session):
    result = run_tool(session, "detect_anomalies", {"dataset": "orders", "column": "region"})
    assert not result.ok and "numeric" in result.error
