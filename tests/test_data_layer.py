import pandas as pd
import pytest

from app.data.charts import build_chart
from app.data.loader import table_name_for, validate_upload
from app.data.sandbox import run_python
from app.errors import UserError
from conftest import DATA_DIR


def csv_bytes(text: str) -> bytes:
    return text.encode("utf-8")


class TestCsvValidation:
    def test_rejects_wrong_extension(self):
        with pytest.raises(UserError) as exc:
            validate_upload("data.xlsx", b"a,b\n1,2", 5)
        assert exc.value.status == 415

    def test_rejects_empty_file(self):
        with pytest.raises(UserError) as exc:
            validate_upload("data.csv", b"   \n", 5)
        assert exc.value.code == "empty_file"

    def test_rejects_huge_file(self):
        with pytest.raises(UserError) as exc:
            validate_upload("data.csv", b"a\n" * (2 * 1024 * 1024), 1)
        assert exc.value.status == 413

    def test_rejects_binary_content(self):
        with pytest.raises(UserError):
            validate_upload("data.csv", b"\x00\x01\x02binary", 5)

    def test_transcodes_latin1(self):
        content = "name\ncaf\xe9".encode("latin-1")
        assert "café" in validate_upload("data.csv", content, 5).decode("utf-8")

    def test_table_names_are_safe_and_unique(self):
        assert table_name_for("My Sales 2024!.csv", set()) == "my_sales_2024"
        assert table_name_for("2024.csv", set()) == "t_2024"
        assert table_name_for("orders.csv", {"orders"}) == "orders_2"

    def test_header_only_csv_is_rejected(self, empty_store):
        with pytest.raises(UserError):
            empty_store.add_csv("empty.csv", csv_bytes("a,b,c\n"))
        assert empty_store.table_names() == set()

    def test_malformed_rows_are_skipped_and_reported(self, empty_store):
        body = "".join(f"{i},{i * 2}\n" for i in range(40)) + "9,9,9,9\n" + "".join(f"{i},1\n" for i in range(40))
        profile = empty_store.add_csv("messy.csv", csv_bytes("a,b\n" + body))
        assert profile.rows >= 70 and profile.column_count == 2
        assert profile.skipped_rows >= 1
        assert any(i.type == "malformed_rows" for i in empty_store.get_quality("messy").issues)

    def test_semicolon_delimiter_is_detected(self, empty_store):
        profile = empty_store.add_csv("semi.csv", csv_bytes("a;b\n1;2\n3;4\n5;6\n"))
        assert profile.column_count == 2 and profile.rows == 3

    def test_dataset_limit(self, settings, empty_store):
        for i in range(settings.max_files_per_session):
            empty_store.add_csv(f"f{i}.csv", csv_bytes("a\n1\n2\n"))
        with pytest.raises(UserError):
            empty_store.add_csv("extra.csv", csv_bytes("a\n1\n"))


class TestSchemaInference:
    def test_sample_profile(self, store):
        profile = store.get_profile("orders")
        kinds = {c.name: c.kind for c in profile.columns}
        assert profile.rows == len(pd.read_csv(DATA_DIR / "orders.csv"))
        assert kinds["order_date"] == "date"
        assert kinds["revenue"] == "numeric"
        assert kinds["region"] == "categorical"
        assert profile.duplicate_rows == 12

    def test_missing_counts_match_pandas(self, store):
        truth = pd.read_csv(DATA_DIR / "orders.csv")
        by_name = {c.name: c for c in store.get_profile("orders").columns}
        assert by_name["discount"].missing == int(truth["discount"].isna().sum())
        assert by_name["revenue"].mean == pytest.approx(truth["revenue"].mean())

    def test_missing_column_error_lists_available(self, store):
        with pytest.raises(UserError) as exc:
            store.get_column("orders", "nonexistent")
        assert "revenue" in exc.value.message


class TestDataQuality:
    def test_flags_each_issue_type(self, empty_store):
        rows = ["id,amount,joined,label,const"]
        for i in range(60):
            amount = "oops" if i == 0 else str(100 + i)
            joined = "not a date" if i == 1 else f"2024-01-{(i % 28) + 1:02d}"
            label = "North" if i % 2 else ("north " if i % 4 == 0 else "South")
            rows.append(f"{i},{amount},{joined},{label},x")
        rows.append(rows[5])
        empty_store.add_csv("q.csv", csv_bytes("\n".join(rows)))
        issues = {(i.type, i.column) for i in empty_store.get_quality("q").issues}
        assert ("invalid_type", "amount") in issues
        assert ("date_parsing", "joined") in issues
        assert ("inconsistent_values", "label") in issues
        assert ("constant_column", "const") in issues
        assert ("duplicate_rows", None) in issues

    def test_sample_orders_flags_negative_revenue_and_missing(self, store):
        issues = {(i.type, i.column) for i in store.get_quality("orders").issues}
        assert ("suspicious_values", "revenue") in issues
        assert ("missing_values", "discount") in issues
        assert store.get_quality("orders").score < 100

    def test_identifier_columns_are_not_flagged_as_extreme(self, store):
        columns = {i.column for i in store.get_quality("orders").issues if i.type == "suspicious_values"}
        assert "order_id" not in columns


class TestSqlExecution:
    def test_aggregation_matches_pandas(self, store):
        truth = pd.read_csv(DATA_DIR / "orders.csv").groupby("region")["revenue"].sum().sort_values(ascending=False)
        result = store.query('SELECT region, sum(revenue) AS total FROM orders GROUP BY region ORDER BY total DESC')
        assert result.rows[0][0] == truth.index[0]
        assert result.rows[0][1] == pytest.approx(truth.iloc[0])

    def test_join_across_files(self, store):
        result = store.query(
            'SELECT c.segment, count(*) FROM orders o JOIN customers c ON o.customer_id = c.customer_id GROUP BY 1'
        )
        assert sum(r[1] for r in result.rows) == store.get_profile("orders").rows

    def test_result_rows_are_capped(self, store):
        result = store.query("SELECT * FROM orders", max_rows=10)
        assert result.row_count == 10 and result.truncated

    @pytest.mark.parametrize("sql", [
        "DROP TABLE orders",
        "DELETE FROM orders",
        "UPDATE orders SET revenue = 0",
        "INSERT INTO orders SELECT * FROM orders",
        "CREATE TABLE x AS SELECT 1",
        "ATTACH 'x.db'",
        "COPY orders TO 'out.csv'",
        "SELECT 1; DROP TABLE orders",
        "PRAGMA database_list",
        "SELECT * FROM read_csv('x.csv')",
        "SELECT * FROM read_parquet('x.parquet')",
        "SELECT * FROM glob('*')",
        "SELECT * FROM duckdb_settings()",
        "SELECT * FROM missing_table",
    ])
    def test_unsafe_or_invalid_sql_is_rejected(self, store, sql):
        with pytest.raises(UserError):
            store.query(sql)
        assert "orders" in store.table_names()

    def test_cte_and_subquery_are_allowed(self, store):
        result = store.query("WITH t AS (SELECT region, revenue FROM orders) SELECT count(*) FROM (SELECT * FROM t)")
        assert result.rows[0][0] > 0

    def test_long_running_query_is_cancelled(self, store):
        store.settings.sql_timeout_seconds = 1
        with pytest.raises(UserError) as exc:
            store.query("SELECT count(*) FROM range(100000000000) a, range(1000000) b")
        assert exc.value.code == "timeout"

    def test_syntax_error_is_user_friendly(self, store):
        with pytest.raises(UserError) as exc:
            store.query("SELEC nothing FROM")
        assert "Traceback" not in exc.value.message

    def test_runtime_error_is_user_friendly(self, store):
        with pytest.raises(UserError) as exc:
            store.query("SELECT nonexistent_column FROM orders")
        assert "nonexistent_column" in exc.value.message


class TestRelationships:
    def test_foreign_keys_are_inferred(self, store):
        pairs = {(r.left_table, r.left_column, r.right_table, r.right_column) for r in store.relationships}
        assert ("orders", "customer_id", "customers", "customer_id") in pairs
        assert ("orders", "product_id", "products", "product_id") in pairs

    def test_many_to_many_name_matches_are_ignored(self, store):
        assert not any(r.left_column == "region" for r in store.relationships)

    def test_user_declared_relationship(self, store):
        relationship = store.add_relationship(("orders", "region"), ("customers", "region"))
        assert relationship.source == "user" and relationship.cardinality == "many-to-many"

    def test_relationship_with_unknown_column_fails(self, store):
        with pytest.raises(UserError):
            store.add_relationship(("orders", "nope"), ("customers", "customer_id"))

    def test_removing_dataset_removes_relationships(self, store):
        store.remove("customers")
        assert all("customers" not in (r.left_table, r.right_table) for r in store.relationships)


class TestVisualizationData:
    def test_bar_chart_values_come_from_query(self, store):
        table = store.query("SELECT region, sum(revenue) AS total FROM orders GROUP BY 1 ORDER BY 2 DESC")
        chart = build_chart(table, "bar", "Revenue by region", "region", ["total"])
        assert chart.data[0]["region"] == table.rows[0][0]
        assert chart.data[0]["total"] == table.rows[0][1]
        assert chart.x_label == "region" and chart.title == "Revenue by region"

    def test_series_are_pivoted(self, store):
        table = store.query(
            "SELECT strftime(order_date, '%Y-%m') AS month, region, sum(revenue) AS rev FROM orders GROUP BY 1, 2 ORDER BY 1"
        )
        chart = build_chart(table, "line", "t", "month", ["rev"], series="region")
        assert set(chart.y_keys) == {"North America", "Europe", "Asia Pacific", "Latin America", "Middle East & Africa"}

    def test_histogram_counts_sum_to_rows(self, store):
        table = store.query("SELECT quantity FROM orders", max_rows=20000)
        chart = build_chart(table, "histogram", "Quantity", "quantity", [], bins=10)
        assert sum(p["count"] for p in chart.data) == len(table.rows)

    def test_scatter_and_pie(self, store):
        table = store.query("SELECT unit_price, revenue FROM orders", max_rows=500)
        assert build_chart(table, "scatter", "t", "unit_price", ["revenue"]).type == "scatter"
        pie = store.query("SELECT channel, count(*) AS n FROM orders WHERE channel IS NOT NULL GROUP BY 1")
        assert len(build_chart(pie, "pie", "t", "channel", ["n"]).data) == 3

    def test_missing_column_and_empty_result_fail_cleanly(self, store):
        table = store.query("SELECT region FROM orders LIMIT 5")
        with pytest.raises(UserError):
            build_chart(table, "bar", "t", "region", ["nope"])
        with pytest.raises(UserError):
            build_chart(store.query("SELECT region FROM orders WHERE 1 = 0"), "bar", "t", "region", ["region"])

    def test_non_numeric_y_is_rejected(self, store):
        table = store.query("SELECT region, channel FROM orders LIMIT 5")
        with pytest.raises(UserError):
            build_chart(table, "bar", "t", "region", ["channel"])


class TestPythonSandbox:
    def run(self, store, code):
        return run_python(code, {"orders": store.parquet_path("orders")}, timeout=5, memory_mb=2048, max_rows=100)

    def test_computes_dataframe_result(self, store):
        out = self.run(store, "result = orders.groupby('region')['revenue'].sum().sort_values(ascending=False)")
        truth = pd.read_csv(DATA_DIR / "orders.csv").groupby("region")["revenue"].sum().max()
        assert out["ok"] and out["result"]["rows"][0][1] == pytest.approx(truth)

    def test_scalar_result_and_stdout(self, store):
        out = self.run(store, "print('hi')\nresult = int(len(orders))")
        assert out["ok"] and out["stdout"].strip() == "hi" and out["result"]["value"] > 7000

    def test_runtime_error_is_reported(self, store):
        out = self.run(store, "result = orders['missing'].sum()")
        assert not out["ok"] and "KeyError" in out["error"]

    def test_missing_result_variable(self, store):
        assert not self.run(store, "x = 1")["ok"]

    @pytest.mark.parametrize("code", [
        "import os\nresult = 1",
        "from os import system\nresult = 1",
        "result = open('/etc/passwd').read()",
        "result = __import__('os').listdir('.')",
        "result = ().__class__.__bases__",
        "result = pd.read_csv('http://example.com/x.csv')",
        "result = orders.to_csv('out.csv')",
        "result = eval('1+1')",
        "result = getattr(orders, 'shape')",
        "result = orders.query('revenue > 1')",
        "result = np.load('x.npy')",
    ])
    def test_dangerous_code_is_rejected(self, store, code):
        with pytest.raises(UserError):
            self.run(store, code)

    def test_infinite_loop_times_out(self, store):
        with pytest.raises(UserError) as exc:
            run_python("while True:\n    pass", {}, timeout=1, memory_mb=2048, max_rows=10)
        assert exc.value.code == "timeout"
