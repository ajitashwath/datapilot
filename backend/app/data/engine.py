import json
import threading
import time
from datetime import date, datetime, time as dtime
from decimal import Decimal
from typing import Any

import duckdb

from app.errors import UserError
from app.logging_setup import log_event
from app.models import TableResult

ALLOWED_TABLE_FUNCTIONS = {"range", "generate_series", "unnest"}
BLOCKED_FUNCTIONS = {
    "glob", "getenv", "current_setting", "load_extension", "install_extension",
    "duckdb_settings", "duckdb_secrets", "which_secret", "pragma_database_size",
    "sniff_csv", "query", "query_table",
}


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return None if value != value or value in (float("inf"), float("-inf")) else value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if hasattr(value, "item"):
        return jsonable(value.item())
    return str(value)


def walk_sql_tree(node: Any, tables: set[str], functions: set[str], table_functions: set[str], ctes: set[str]) -> None:
    if isinstance(node, dict):
        if node.get("type") == "BASE_TABLE":
            tables.add(node.get("table_name", ""))
        if node.get("type") == "TABLE_FUNCTION":
            table_functions.add(str(node.get("function", {}).get("function_name", "")).lower())
        if "function_name" in node:
            functions.add(str(node["function_name"]).lower())
        cte_map = node.get("cte_map")
        if isinstance(cte_map, dict):
            for entry in cte_map.get("map", []):
                ctes.add(entry.get("key", ""))
        for value in node.values():
            walk_sql_tree(value, tables, functions, table_functions, ctes)
    elif isinstance(node, list):
        for item in node:
            walk_sql_tree(item, tables, functions, table_functions, ctes)


def validate_select(con: duckdb.DuckDBPyConnection, sql: str, allowed_tables: set[str]) -> str:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise UserError("The SQL query is empty.")
    if len(sql) > 8000:
        raise UserError("The SQL query is too long.")
    try:
        statements = con.extract_statements(sql)
    except duckdb.Error as exc:
        raise UserError(f"The SQL could not be parsed: {first_line(exc)}") from exc
    if len(statements) != 1:
        raise UserError("Only a single SQL statement is allowed.")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise UserError("Only read-only SELECT queries are allowed.")
    raw = con.execute("SELECT json_serialize_sql(?)", [sql]).fetchone()[0]
    tree = json.loads(raw)
    if tree.get("error"):
        raise UserError(f"The SQL is not supported: {tree.get('error_message', 'unsupported query')}")
    tables: set[str] = set()
    functions: set[str] = set()
    table_functions: set[str] = set()
    ctes: set[str] = set()
    walk_sql_tree(tree, tables, functions, table_functions, ctes)
    blocked = {f for f in functions if f in BLOCKED_FUNCTIONS or f.startswith("read_")}
    blocked |= {f for f in table_functions if f not in ALLOWED_TABLE_FUNCTIONS}
    if blocked:
        raise UserError(f"These functions are not allowed: {', '.join(sorted(blocked))}.")
    unknown = {t for t in tables if t not in allowed_tables and t not in ctes}
    if unknown:
        raise UserError(
            f"Unknown table(s): {', '.join(sorted(unknown))}. Available tables: {', '.join(sorted(allowed_tables))}."
        )
    return sql


def first_line(exc: Exception) -> str:
    return str(exc).strip().splitlines()[0][:300]


def run_select(
    con: duckdb.DuckDBPyConnection,
    sql: str,
    allowed_tables: set[str],
    max_rows: int,
    timeout: float,
) -> TableResult:
    sql = validate_select(con, sql, allowed_tables)
    cursor = con.cursor()
    timer = threading.Timer(timeout, cursor.interrupt)
    started = time.perf_counter()
    timer.start()
    try:
        cursor.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchmany(max_rows + 1)
    except duckdb.InterruptException as exc:
        raise UserError(f"The query took longer than {timeout:.0f} seconds and was cancelled.", "timeout") from exc
    except duckdb.Error as exc:
        raise UserError(f"The query failed: {first_line(exc)}") from exc
    finally:
        timer.cancel()
        cursor.close()
    log_event("query_executed", duration_ms=round((time.perf_counter() - started) * 1000, 1), rows=len(rows))
    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return TableResult(
        columns=columns,
        rows=[[jsonable(v) for v in row] for row in rows],
        row_count=len(rows),
        truncated=truncated,
    )
