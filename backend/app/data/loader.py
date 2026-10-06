import csv
import re
import uuid
from pathlib import Path

import duckdb

from app.errors import UserError

ALLOWED_EXTENSIONS = {".csv"}


def validate_upload(filename: str, content: bytes, max_mb: int) -> bytes:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UserError(f"'{filename}' is not supported. Please upload a .csv file.", "unsupported_file", 415)
    if len(content) > max_mb * 1024 * 1024:
        raise UserError(f"'{filename}' is larger than the {max_mb} MB limit.", "file_too_large", 413)
    if not content.strip():
        raise UserError(f"'{filename}' is empty.", "empty_file", 422)
    if b"\x00" in content[:8192]:
        raise UserError(f"'{filename}' looks like a binary file, not a CSV.", "invalid_csv", 422)
    try:
        content.decode("utf-8-sig")
        return content
    except UnicodeDecodeError:
        return content.decode("latin-1").encode("utf-8")


def table_name_for(filename: str, existing: set[str]) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", Path(filename).stem.lower()).strip("_") or "dataset"
    if stem[0].isdigit():
        stem = "t_" + stem
    name, counter = stem, 2
    while name in existing:
        name = f"{stem}_{counter}"
        counter += 1
    return name


def save_upload(directory: Path, content: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex}.csv"
    path.write_bytes(content)
    return path


def detect_delimiter(path: Path) -> str:
    sample = path.read_text(encoding="utf-8-sig", errors="replace")[:65536]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;	|").delimiter
    except csv.Error:
        return ","


def load_csv_table(con: duckdb.DuckDBPyConnection, table: str, path: Path, filename: str) -> int:
    quoted = '"' + table + '"'
    delim = detect_delimiter(path)
    try:
        con.execute(f"CREATE TABLE {quoted} AS SELECT * FROM read_csv(?, header=true, sample_size=-1, delim=?)", [str(path), delim])
        return 0
    except duckdb.Error:
        con.execute(f"DROP TABLE IF EXISTS {quoted}")
    try:
        con.execute(
            f"CREATE TABLE {quoted} AS SELECT * FROM read_csv(?, header=true, sample_size=-1, "
            "delim=?, ignore_errors=true, store_rejects=true)",
            [str(path), delim],
        )
    except duckdb.Error as exc:
        con.execute(f"DROP TABLE IF EXISTS {quoted}")
        raise UserError(f"'{filename}' could not be parsed as a CSV file.", "invalid_csv", 422) from exc
    skipped = con.execute("SELECT count(DISTINCT line) FROM reject_errors").fetchone()[0]
    con.execute("DROP TABLE IF EXISTS reject_errors")
    con.execute("DROP TABLE IF EXISTS reject_scans")
    return skipped
