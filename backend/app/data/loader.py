import codecs
import csv
import re
import shutil
from pathlib import Path

import duckdb

from app.errors import UserError

ALLOWED_EXTENSIONS = {".csv"}
CHUNK_BYTES = 1024 * 1024


def validate_file(filename: str, path: Path, max_mb: int) -> None:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise UserError(f"'{filename}' is not supported. Please upload a .csv file.", "unsupported_file", 415)
    if path.stat().st_size > max_mb * 1024 * 1024:
        raise UserError(f"'{filename}' is larger than the {max_mb} MB limit.", "file_too_large", 413)
    with path.open("rb") as handle:
        head = handle.read(65536)
    if not head.strip():
        raise UserError(f"'{filename}' is empty.", "empty_file", 422)
    if b"\x00" in head[:8192]:
        raise UserError(f"'{filename}' looks like a binary file, not a CSV.", "invalid_csv", 422)


def ensure_utf8(path: Path) -> Path:
    decoder = codecs.getincrementaldecoder("utf-8-sig")()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(CHUNK_BYTES):
                decoder.decode(chunk)
        decoder.decode(b"", final=True)
        return path
    except UnicodeDecodeError:
        converted = path.with_name(path.stem + ".utf8.csv")
        with path.open("r", encoding="latin-1", newline="") as source, converted.open("w", encoding="utf-8", newline="") as target:
            shutil.copyfileobj(source, target)
        path.unlink()
        return converted


def table_name_for(filename: str, existing: set[str]) -> str:
    stem = re.sub(r"[^a-z0-9]+", "_", Path(filename).stem.lower()).strip("_") or "dataset"
    if stem[0].isdigit():
        stem = "t_" + stem
    name, counter = stem, 2
    while name in existing:
        name = f"{stem}_{counter}"
        counter += 1
    return name


def detect_delimiter(path: Path) -> str:
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        sample = handle.read(65536)
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
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
