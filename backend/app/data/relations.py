import duckdb

from app.data.profiler import quote
from app.models import DatasetProfile, Relationship

JOINABLE_KINDS = {"numeric", "categorical", "text", "date"}


def singular(table: str) -> str:
    return table[:-1] if table.endswith("s") else table


def names_match(left_table: str, left_col: str, right_table: str, right_col: str) -> bool:
    a, b = left_col.lower(), right_col.lower()
    if a == b:
        return True
    if b == "id" and a == f"{singular(right_table)}_id":
        return True
    return a == "id" and b == f"{singular(left_table)}_id"


def column_stats(con: duckdb.DuckDBPyConnection, table: str, column: str) -> tuple[int, int]:
    return con.execute(f"SELECT count({quote(column)}), count(DISTINCT {quote(column)}) FROM {quote(table)}").fetchone()


def overlap_pct(con: duckdb.DuckDBPyConnection, left: tuple[str, str], right: tuple[str, str]) -> float:
    sql = (
        f"WITH a AS (SELECT DISTINCT CAST({quote(left[1])} AS VARCHAR) v FROM {quote(left[0])} WHERE {quote(left[1])} IS NOT NULL), "
        f"b AS (SELECT DISTINCT CAST({quote(right[1])} AS VARCHAR) v FROM {quote(right[0])} WHERE {quote(right[1])} IS NOT NULL) "
        "SELECT (SELECT count(*) FROM a), (SELECT count(*) FROM a WHERE v IN (SELECT v FROM b)), "
        "(SELECT count(*) FROM b), (SELECT count(*) FROM b WHERE v IN (SELECT v FROM a))"
    )
    total_a, hit_a, total_b, hit_b = con.execute(sql).fetchone()
    if not total_a or not total_b:
        return 0.0
    return round(max(hit_a / total_a, hit_b / total_b) * 100, 1)


def cardinality_for(con: duckdb.DuckDBPyConnection, left: tuple[str, str], right: tuple[str, str]) -> str:
    left_count, left_distinct = column_stats(con, *left)
    right_count, right_distinct = column_stats(con, *right)
    left_unique = left_count == left_distinct
    right_unique = right_count == right_distinct
    if left_unique and right_unique:
        return "one-to-one"
    if left_unique:
        return "one-to-many"
    return "many-to-one" if right_unique else "many-to-many"


def measure_relationship(
    con: duckdb.DuckDBPyConnection, left: tuple[str, str], right: tuple[str, str], source: str = "inferred"
) -> Relationship:
    return Relationship(
        left_table=left[0], left_column=left[1], right_table=right[0], right_column=right[1],
        cardinality=cardinality_for(con, left, right), overlap_pct=overlap_pct(con, left, right), source=source,
    )


def infer_between(con: duckdb.DuckDBPyConnection, left: DatasetProfile, right: DatasetProfile) -> list[Relationship]:
    found = []
    for lc in left.columns:
        for rc in right.columns:
            if lc.kind not in JOINABLE_KINDS or rc.kind not in JOINABLE_KINDS:
                continue
            if (lc.kind == "numeric") != (rc.kind == "numeric"):
                continue
            if not names_match(left.name, lc.name, right.name, rc.name):
                continue
            if lc.distinct <= 1 or rc.distinct <= 1:
                continue
            relationship = measure_relationship(con, (left.name, lc.name), (right.name, rc.name))
            if relationship.overlap_pct >= 80 and relationship.cardinality != "many-to-many":
                found.append(relationship)
    return found
