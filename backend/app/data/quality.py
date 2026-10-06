import duckdb

from app.data.profiler import is_identifier, quote
from app.models import ColumnProfile, DatasetProfile, QualityIssue, QualityReport

PENALTY = {"low": 2, "medium": 6, "high": 15}


def severity_for_missing(pct: float) -> str:
    if pct >= 30:
        return "high"
    return "medium" if pct >= 5 else "low"


def check_text_column(con: duckdb.DuckDBPyConnection, table: str, col: ColumnProfile) -> list[QualityIssue]:
    issues = []
    name = quote(col.name)
    non_null = con.execute(f"SELECT count({name}) FROM {quote(table)}").fetchone()[0]
    if not non_null:
        return issues
    numeric_ok = con.execute(f"SELECT count(TRY_CAST({name} AS DOUBLE)) FROM {quote(table)}").fetchone()[0]
    if numeric_ok >= non_null * 0.8 and numeric_ok < non_null:
        bad = con.execute(
            f"SELECT {name} FROM {quote(table)} WHERE {name} IS NOT NULL AND TRY_CAST({name} AS DOUBLE) IS NULL LIMIT 3"
        ).fetchall()
        issues.append(QualityIssue(
            severity="medium", type="invalid_type", column=col.name, count=non_null - numeric_ok,
            message=f"'{col.name}' looks numeric but {non_null - numeric_ok} values are not numbers (for example {[b[0] for b in bad]}).",
        ))
    date_ok = con.execute(f"SELECT count(TRY_CAST({name} AS TIMESTAMP)) FROM {quote(table)}").fetchone()[0]
    if date_ok >= non_null * 0.5 and date_ok < non_null and numeric_ok < non_null * 0.5:
        bad = con.execute(
            f"SELECT {name} FROM {quote(table)} WHERE {name} IS NOT NULL AND TRY_CAST({name} AS TIMESTAMP) IS NULL LIMIT 3"
        ).fetchall()
        issues.append(QualityIssue(
            severity="medium", type="date_parsing", column=col.name, count=non_null - date_ok,
            message=f"'{col.name}' looks like a date column but {non_null - date_ok} values could not be parsed (for example {[b[0] for b in bad]}).",
        ))
    folded = con.execute(f"SELECT count(DISTINCT lower(trim({name}))) FROM {quote(table)}").fetchone()[0]
    if folded < col.distinct:
        issues.append(QualityIssue(
            severity="medium", type="inconsistent_values", column=col.name, count=col.distinct - folded,
            message=f"'{col.name}' has {col.distinct - folded} values that differ only by case or surrounding spaces.",
        ))
    return issues


def check_numeric_column(con: duckdb.DuckDBPyConnection, table: str, col: ColumnProfile) -> list[QualityIssue]:
    issues = []
    name = quote(col.name)
    if col.min is not None and col.min < 0 and col.q1 is not None and col.q1 >= 0:
        negatives = con.execute(f"SELECT count(*) FROM {quote(table)} WHERE {name} < 0").fetchone()[0]
        issues.append(QualityIssue(
            severity="medium", type="suspicious_values", column=col.name, count=negatives,
            message=f"'{col.name}' has {negatives} negative value{'s' if negatives != 1 else ''} although most values are non-negative.",
        ))
    if col.q1 is not None and col.q3 is not None and col.q3 > col.q1:
        iqr = col.q3 - col.q1
        low, high = col.q1 - 3 * iqr, col.q3 + 3 * iqr
        extreme = con.execute(
            f"SELECT count(*) FROM {quote(table)} WHERE {name} < ? OR {name} > ?", [low, high]
        ).fetchone()[0]
        if extreme:
            issues.append(QualityIssue(
                severity="low", type="suspicious_values", column=col.name, count=extreme,
                message=f"'{col.name}' has {extreme} extreme values outside {low:,.2f} to {high:,.2f} (3 x IQR).",
            ))
    return issues


def check_quality(con: duckdb.DuckDBPyConnection, profile: DatasetProfile) -> QualityReport:
    issues: list[QualityIssue] = []
    for col in profile.columns:
        if col.missing:
            issues.append(QualityIssue(
                severity=severity_for_missing(col.missing_pct), type="missing_values", column=col.name, count=col.missing,
                message=f"'{col.name}' is missing {col.missing} values ({col.missing_pct}%).",
            ))
        if col.distinct <= 1 and profile.rows > 1 and col.missing < profile.rows:
            issues.append(QualityIssue(
                severity="low", type="constant_column", column=col.name, count=profile.rows,
                message=f"'{col.name}' has a single value and carries no information.",
            ))
        if col.kind in ("categorical", "text") and col.dtype.upper() == "VARCHAR":
            non_null = profile.rows - col.missing
            if col.distinct > 50 and non_null and col.distinct / non_null > 0.9:
                issues.append(QualityIssue(
                    severity="low", type="high_cardinality", column=col.name, count=col.distinct,
                    message=f"'{col.name}' has {col.distinct} distinct values and is probably an identifier or free text.",
                ))
            issues.extend(check_text_column(con, profile.name, col))
        if col.kind == "numeric" and not is_identifier(col, profile.rows):
            issues.extend(check_numeric_column(con, profile.name, col))
    if profile.duplicate_rows:
        pct = profile.duplicate_rows / profile.rows * 100
        issues.append(QualityIssue(
            severity="medium" if pct >= 1 else "low", type="duplicate_rows", count=profile.duplicate_rows,
            message=f"{profile.duplicate_rows} duplicate rows ({pct:.2f}% of the data).",
        ))
    if profile.skipped_rows:
        issues.append(QualityIssue(
            severity="high", type="malformed_rows", count=profile.skipped_rows,
            message=f"{profile.skipped_rows} malformed rows were skipped while reading the file.",
        ))
    order = {"high": 0, "medium": 1, "low": 2}
    issues.sort(key=lambda i: order[i.severity])
    penalty = sum(PENALTY[i.severity] for i in issues)
    return QualityReport(dataset=profile.name, score=max(0, 100 - penalty), issues=issues)
