import duckdb

from app.models import ColumnProfile, DatasetProfile, TopValue
from app.data.engine import jsonable

NUMERIC_PREFIXES = ("TINYINT", "SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "UTINYINT", "USMALLINT", "UINTEGER", "UBIGINT", "UHUGEINT", "FLOAT", "DOUBLE", "DECIMAL")


def quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def is_identifier(col: ColumnProfile, rows: int) -> bool:
    name = col.name.lower()
    integer = "INT" in col.dtype.upper()
    return integer and (name == "id" or name.endswith("_id") or col.distinct == rows)


def kind_for(dtype: str, distinct: int, rows: int) -> str:
    upper = dtype.upper()
    if upper.startswith(NUMERIC_PREFIXES):
        return "numeric"
    if upper.startswith(("DATE", "TIMESTAMP")):
        return "date"
    if upper == "BOOLEAN":
        return "boolean"
    if distinct <= 50 and distinct <= max(rows * 0.5, 2):
        return "categorical"
    return "text"


def profile_column(con: duckdb.DuckDBPyConnection, table: str, name: str, dtype: str, rows: int) -> ColumnProfile:
    col = quote(name)
    non_null, distinct = con.execute(f"SELECT count({col}), count(DISTINCT {col}) FROM {quote(table)}").fetchone()
    kind = kind_for(dtype, distinct, rows)
    profile = ColumnProfile(
        name=name,
        dtype=dtype,
        kind=kind,
        missing=rows - non_null,
        missing_pct=round((rows - non_null) / rows * 100, 2) if rows else 0.0,
        distinct=distinct,
    )
    if non_null == 0:
        return profile
    if kind == "numeric":
        row = con.execute(
            f"SELECT min({col}), max({col}), avg({col}), stddev_samp({col}), median({col}), "
            f"quantile_cont({col}, 0.25), quantile_cont({col}, 0.75) FROM {quote(table)}"
        ).fetchone()
        profile.min, profile.max = jsonable(row[0]), jsonable(row[1])
        profile.mean, profile.std, profile.median, profile.q1, profile.q3 = [
            None if v is None else float(v) for v in row[2:]
        ]
    elif kind == "date":
        low, high = con.execute(f"SELECT min({col}), max({col}) FROM {quote(table)}").fetchone()
        profile.min, profile.max = jsonable(low), jsonable(high)
    if kind in ("categorical", "text", "boolean"):
        top = con.execute(
            f"SELECT {col}, count(*) c FROM {quote(table)} WHERE {col} IS NOT NULL GROUP BY {col} ORDER BY c DESC, 1 LIMIT 5"
        ).fetchall()
        profile.top_values = [TopValue(value=jsonable(v), count=c) for v, c in top]
    samples = con.execute(f"SELECT DISTINCT {col} FROM {quote(table)} WHERE {col} IS NOT NULL LIMIT 4").fetchall()
    profile.samples = [jsonable(s[0]) for s in samples]
    return profile


def profile_dataset(con: duckdb.DuckDBPyConnection, table: str, filename: str, skipped_rows: int = 0) -> DatasetProfile:
    rows = con.execute(f"SELECT count(*) FROM {quote(table)}").fetchone()[0]
    described = con.execute(f"SELECT column_name, column_type FROM (DESCRIBE {quote(table)})").fetchall()
    unique_rows = con.execute(f"SELECT count(*) FROM (SELECT DISTINCT * FROM {quote(table)})").fetchone()[0]
    columns = [profile_column(con, table, name, dtype, rows) for name, dtype in described]
    return DatasetProfile(
        name=table,
        filename=filename,
        rows=rows,
        column_count=len(columns),
        duplicate_rows=rows - unique_rows,
        skipped_rows=skipped_rows,
        columns=columns,
    )
