import ipaddress
import re
import socket
import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import pandas as pd
from pydantic import BaseModel, Field, SecretStr

from app.config import Settings
from app.data.profiler import quote
from app.errors import UserError
from app.logging_setup import log_event
from app.session import Session

SQLITE_MAGIC = b"SQLite format 3\x00"
MAX_REDIRECTS = 3
SHEETS_PATH = re.compile(r"^/spreadsheets/d/([A-Za-z0-9_-]{20,})")
HTML_START = re.compile(rb"^\s*(<!doctype html|<html)", re.IGNORECASE)
POSTGRES_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


class PostgresConnection(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(5432, ge=1, le=65535)
    dbname: str = Field(min_length=1, max_length=63)
    user: str = Field(min_length=1, max_length=63)
    password: SecretStr = Field(max_length=200)
    sslmode: str = Field("require", pattern="^(require|prefer|disable)$")


def public_addresses(host: str, port: int, allow_private: bool) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UserError(f"Could not resolve the host '{host}'.", "unresolvable_host", 422) from exc
    addresses = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        ip = ip.ipv4_mapped or ip if isinstance(ip, ipaddress.IPv6Address) else ip
        if not allow_private and not ip.is_global:
            raise UserError("That address is not publicly reachable, so it cannot be imported from.", "blocked_address", 422)
        addresses.append(str(ip))
    if not addresses:
        raise UserError(f"Could not resolve the host '{host}'.", "unresolvable_host", 422)
    return addresses


def normalise_url(url: str, allow_private: bool) -> str:
    parsed = urlparse(url.strip())
    allowed = ("https", "http") if allow_private else ("https",)
    if parsed.scheme not in allowed or not parsed.hostname:
        raise UserError("Enter a full https:// link to a CSV file or a shared Google Sheet.", "invalid_url", 422)
    if parsed.username or parsed.password:
        raise UserError("Links with embedded credentials are not allowed.", "invalid_url", 422)
    if parsed.hostname == "docs.google.com":
        match = SHEETS_PATH.match(parsed.path)
        if match:
            gid = parse_qs(parsed.query).get("gid") or parse_qs(parsed.fragment).get("gid") or ["0"]
            gid = gid[0] if gid[0].isdigit() else "0"
            return f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=csv&gid={gid}"
    return parsed.geturl()


def pinned_request(url: str, allow_private: bool) -> tuple[str, dict, dict]:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    address = public_addresses(parsed.hostname, port, allow_private)[0]
    host_literal = f"[{address}]" if ":" in address else address
    netloc = f"{host_literal}:{port}"
    pinned = parsed._replace(netloc=netloc).geturl()
    return pinned, {"Host": parsed.netloc, "Accept": "text/csv,text/plain,*/*"}, {"sni_hostname": parsed.hostname}


def download_to(path: Path, url: str, settings: Settings, transport: httpx.BaseTransport | None = None) -> str:
    limit = settings.max_upload_mb * 1024 * 1024
    deadline = time.monotonic() + settings.connector_timeout_seconds * 2
    current = url
    with httpx.Client(transport=transport, timeout=settings.connector_timeout_seconds, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            current = normalise_url(current, settings.allow_private_connections)
            target, headers, extensions = pinned_request(current, settings.allow_private_connections)
            try:
                with client.stream("GET", target, headers=headers, extensions=extensions) as response:
                    if response.is_redirect:
                        location = response.headers.get("location", "")
                        current = str(httpx.URL(current).join(location))
                        continue
                    if response.status_code != 200:
                        raise UserError(f"The server answered with status {response.status_code}, not a downloadable file.", "download_failed", 422)
                    written, first = 0, b""
                    with path.open("wb") as handle:
                        for chunk in response.iter_bytes(1024 * 1024):
                            if not first:
                                first = chunk[:512]
                            written += len(chunk)
                            if written > limit or time.monotonic() > deadline:
                                raise UserError(f"The file is larger than the {settings.max_upload_mb} MB limit or took too long to download.", "file_too_large", 413)
                            handle.write(chunk)
                    if HTML_START.match(first):
                        raise UserError(
                            "The link returned a web page, not CSV data. For Google Sheets, share the sheet with anyone who has the link.",
                            "not_csv", 422,
                        )
                    return Path(unquote(urlparse(current).path)).name or "import.csv"
            except httpx.TimeoutException as exc:
                raise UserError("The server took too long to respond.", "download_timeout", 422) from exc
            except httpx.HTTPError as exc:
                raise UserError("The file could not be downloaded from that link.", "download_failed", 422) from exc
    raise UserError("The link redirected too many times.", "too_many_redirects", 422)


def csv_name(filename: str) -> str:
    stem = Path(filename).stem or "import"
    return stem + ".csv"


def import_url(session: Session, settings: Settings, url: str, name: str | None, transport: httpx.BaseTransport | None = None) -> list[str]:
    clean = normalise_url(url, settings.allow_private_connections)
    destination = session.store.incoming_path()
    try:
        filename = download_to(destination, clean, settings, transport)
        label = csv_name(name or ("sheet" if "/export?format=csv" in clean else filename))
        profile = session.store.add_csv_path(label, destination, source=f"url:{clean}")
    finally:
        destination.unlink(missing_ok=True)
    log_event("connector_url_imported", host=urlparse(clean).hostname, rows=profile.rows)
    return [profile.name]


def refresh_sources(session: Session, settings: Settings, transport: httpx.BaseTransport | None = None) -> str:
    refreshed, failed = [], []
    for name, profile in list(session.store.profiles.items()):
        if not profile.source or not profile.source.startswith("url:"):
            continue
        destination = session.store.incoming_path()
        try:
            download_to(destination, profile.source[4:], settings, transport)
            session.store.replace_csv_path(name, destination, profile.source)
            refreshed.append(name)
        except UserError as exc:
            failed.append(f"{name}: {exc.message}")
        finally:
            destination.unlink(missing_ok=True)
    parts = []
    if refreshed:
        parts.append("Refreshed " + ", ".join(refreshed))
    if failed:
        parts.append("Failed " + "; ".join(failed))
    return ". ".join(parts)


def refresh_dataset(session: Session, settings: Settings, name: str, transport: httpx.BaseTransport | None = None) -> list[str]:
    profile = session.store.get_profile(name)
    if not profile.source or not profile.source.startswith("url:"):
        raise UserError("Only datasets imported from a link can be refreshed.", "not_refreshable", 422)
    destination = session.store.incoming_path()
    try:
        download_to(destination, profile.source[4:], settings, transport)
        session.store.replace_csv_path(name, destination, profile.source)
    finally:
        destination.unlink(missing_ok=True)
    return [name]


def import_sqlite(session: Session, settings: Settings, path: Path, filename: str) -> list[str]:
    with path.open("rb") as handle:
        if handle.read(16) != SQLITE_MAGIC:
            raise UserError(f"'{filename}' is not a SQLite database file.", "invalid_sqlite", 422)
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    created = []
    try:
        tables = [r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        if not tables:
            raise UserError(f"'{filename}' contains no tables.", "empty_file", 422)
        room = settings.max_files_per_session - len(session.store.profiles)
        for table in tables[: max(room, 0)]:
            frame = pd.read_sql_query(f"SELECT * FROM {quote(table)} LIMIT {int(settings.connector_max_rows)}", connection)
            if frame.empty:
                continue
            destination = session.store.incoming_path()
            try:
                frame.to_csv(destination, index=False)
                profile = session.store.add_csv_path(csv_name(table), destination, source=f"sqlite:{filename}:{table}")
                created.append(profile.name)
            finally:
                destination.unlink(missing_ok=True)
    except sqlite3.DatabaseError as exc:
        raise UserError(f"'{filename}' could not be read as a SQLite database.", "invalid_sqlite", 422) from exc
    finally:
        connection.close()
    if not created:
        raise UserError(f"'{filename}' has no tables with rows to import.", "empty_file", 422)
    return created


def open_postgres(conn: PostgresConnection, settings: Settings, connect: Callable | None = None):
    public_addresses(conn.host, conn.port, settings.allow_private_connections)
    if connect is None:
        try:
            import psycopg
        except ImportError as exc:
            raise UserError("Postgres support is not installed on this server.", "connector_unavailable", 501) from exc
        connect = psycopg.connect
    try:
        connection = connect(
            host=conn.host, port=conn.port, dbname=conn.dbname, user=conn.user, password=conn.password.get_secret_value(),
            sslmode=conn.sslmode, connect_timeout=10, options="-c default_transaction_read_only=on -c statement_timeout=60000",
        )
    except Exception as exc:
        raise UserError("Could not connect to that Postgres database. Check the host, credentials and SSL setting.", "connection_failed", 422) from exc
    return connection


def list_postgres_tables(conn: PostgresConnection, settings: Settings, connect: Callable | None = None) -> list[str]:
    connection = open_postgres(conn, settings, connect)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_schema, table_name FROM information_schema.tables WHERE table_schema <> ALL(%s) "
                "AND table_type IN ('BASE TABLE', 'VIEW') ORDER BY table_schema, table_name",
                (list(POSTGRES_SYSTEM_SCHEMAS),),
            )
            return [f"{schema}.{table}" for schema, table in cursor.fetchall()]
    finally:
        connection.close()


def import_postgres(
    session: Session, settings: Settings, conn: PostgresConnection, tables: list[str], connect: Callable | None = None
) -> list[str]:
    if not tables:
        raise UserError("Choose at least one table to import.", "no_tables", 422)
    available = set(list_postgres_tables(conn, settings, connect))
    unknown = [t for t in tables if t not in available]
    if unknown:
        raise UserError(f"These tables do not exist: {', '.join(unknown)}.", "unknown_table", 422)
    connection = open_postgres(conn, settings, connect)
    created = []
    try:
        for qualified in tables:
            schema, table = qualified.split(".", 1)
            destination = session.store.incoming_path()
            try:
                with connection.cursor() as cursor, destination.open("wb") as handle:
                    statement = f"COPY (SELECT * FROM {quote(schema)}.{quote(table)} LIMIT {int(settings.connector_max_rows)}) TO STDOUT WITH (FORMAT CSV, HEADER)"
                    with cursor.copy(statement) as copy:
                        for chunk in copy:
                            handle.write(bytes(chunk))
                label = csv_name(table)
                profile = session.store.add_csv_path(label, destination, source=f"postgres:{conn.host}/{conn.dbname}:{qualified}")
                created.append(profile.name)
            finally:
                destination.unlink(missing_ok=True)
    finally:
        connection.close()
    return created
