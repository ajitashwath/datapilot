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


def distinct_values(table: str, column: str) -> str:
    return f"SELECT DISTINCT CAST({quote(column)} AS VARCHAR) AS v FROM {quote(table)} WHERE {quote(column)} IS NOT NULL"


def share_of_matches(con: duckdb.DuckDBPyConnection, left: tuple[str, str], right: tuple[str, str]) -> float:
    total, hits = con.execute(
        f"SELECT count(*), count(y.v) FROM ({distinct_values(*left)}) x LEFT JOIN ({distinct_values(*right)}) y ON x.v = y.v"
    ).fetchone()
    return hits / total if total else 0.0


def overlap_pct(con: duckdb.DuckDBPyConnection, left: tuple[str, str], right: tuple[str, str]) -> float:
    return round(max(share_of_matches(con, left, right), share_of_matches(con, right, left)) * 100, 1)


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
