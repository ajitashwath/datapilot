import json
import shutil
import uuid
from pathlib import Path

import duckdb

from app.config import Settings
from app.data.engine import run_select
from app.data.loader import ensure_utf8, load_csv_table, table_name_for, validate_file
from app.data.profiler import profile_dataset, quote
from app.data.quality import check_quality
from app.data.relations import infer_between, measure_relationship
from app.errors import UserError
from app.models import DatasetProfile, QualityReport, Relationship, TableResult

META_FILE = "meta.json"


class DatasetStore:
    def __init__(self, directory: Path, settings: Settings):
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.settings = settings
        self.con = duckdb.connect(str(directory / "store.duckdb"))
        self.con.execute(f"SET memory_limit='{settings.duckdb_memory_limit}'")
        self.con.execute("SET threads=2")
        self.con.execute(f"SET temp_directory='{(directory / 'spill').as_posix()}'")
        self.profiles: dict[str, DatasetProfile] = {}
        self.quality: dict[str, QualityReport] = {}
        self.relationships: list[Relationship] = []
        self.load_meta()

    def load_meta(self) -> None:
        meta_path = self.directory / META_FILE
        if not meta_path.exists():
            return
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        existing = {row[0] for row in self.con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        self.profiles = {p["name"]: DatasetProfile(**p) for p in meta["datasets"] if p["name"] in existing}
        self.relationships = [
            Relationship(**r) for r in meta["relationships"]
            if r["left_table"] in self.profiles and r["right_table"] in self.profiles
        ]

    def save(self) -> None:
        meta = {
            "datasets": [p.model_dump(mode="json") for p in self.profiles.values()],
            "relationships": [r.model_dump(mode="json") for r in self.relationships],
        }
        temporary = self.directory / (META_FILE + ".tmp")
        temporary.write_text(json.dumps(meta), encoding="utf-8")
        temporary.replace(self.directory / META_FILE)

    def table_names(self) -> set[str]:
        return set(self.profiles)

    def incoming_path(self) -> Path:
        folder = self.directory / "incoming"
        folder.mkdir(exist_ok=True)
        return folder / f"{uuid.uuid4().hex}.csv"

    def add_csv(self, filename: str, content: bytes) -> DatasetProfile:
        path = self.incoming_path()
        path.write_bytes(content)
        return self.add_csv_path(filename, path)

    def add_csv_path(self, filename: str, path: Path, source: str | None = None) -> DatasetProfile:
        try:
            if len(self.profiles) >= self.settings.max_files_per_session:
                raise UserError(f"A session can hold at most {self.settings.max_files_per_session} datasets.", "too_many_files", 422)
            validate_file(filename, path, self.settings.max_upload_mb)
            path = ensure_utf8(path)
            name = table_name_for(filename, self.table_names())
            skipped = load_csv_table(self.con, name, path, filename)
            profile = profile_dataset(self.con, name, filename, skipped)
            profile.source = source
            if profile.rows == 0 or profile.column_count == 0:
                self.con.execute(f"DROP TABLE IF EXISTS {quote(name)}")
                raise UserError(f"'{filename}' has a header but no data rows.", "empty_file", 422)
        finally:
            for leftover in (path, path.with_name(path.stem + ".utf8.csv")):
                leftover.unlink(missing_ok=True)
        for other in self.profiles.values():
            self.relationships.extend(infer_between(self.con, profile, other))
        self.profiles[name] = profile
        self.save()
        return profile

    def replace_csv_path(self, name: str, path: Path, source: str | None) -> DatasetProfile:
        old = self.get_profile(name)
        staging = "dp_refresh_staging"
        try:
            validate_file(old.filename, path, self.settings.max_upload_mb)
            path = ensure_utf8(path)
            self.con.execute(f"DROP TABLE IF EXISTS {quote(staging)}")
            skipped = load_csv_table(self.con, staging, path, old.filename)
            if self.con.execute(f"SELECT count(*) FROM {quote(staging)}").fetchone()[0] == 0:
                raise UserError(f"The refreshed data for '{name}' has no rows, so the existing data was kept.", "empty_file", 422)
            self.con.execute(f"DROP TABLE {quote(name)}")
            self.con.execute(f"ALTER TABLE {quote(staging)} RENAME TO {quote(name)}")
        finally:
            self.con.execute(f"DROP TABLE IF EXISTS {quote(staging)}")
            for leftover in (path, path.with_name(path.stem + ".utf8.csv")):
                leftover.unlink(missing_ok=True)
        profile = profile_dataset(self.con, name, old.filename, skipped)
        profile.source = source
        self.profiles[name] = profile
        self.quality.pop(name, None)
        shutil.rmtree(self.directory / f"parquet_{name}", ignore_errors=True)
        self.save()
        return profile

    def remove(self, name: str) -> None:
        self.get_profile(name)
        self.con.execute(f"DROP TABLE IF EXISTS {quote(name)}")
        del self.profiles[name]
        self.quality.pop(name, None)
        self.relationships = [r for r in self.relationships if name not in (r.left_table, r.right_table)]
        shutil.rmtree(self.directory / f"parquet_{name}", ignore_errors=True)
        self.save()

    def get_profile(self, name: str) -> DatasetProfile:
        if name not in self.profiles:
            available = ", ".join(sorted(self.profiles)) or "none"
            raise UserError(f"Dataset '{name}' does not exist. Available datasets: {available}.", "dataset_not_found", 404)
        return self.profiles[name]

    def get_column(self, dataset: str, column: str):
        profile = self.get_profile(dataset)
        for col in profile.columns:
            if col.name == column:
                return col
        available = ", ".join(c.name for c in profile.columns)
        raise UserError(f"Column '{column}' does not exist in '{dataset}'. Available columns: {available}.", "column_not_found", 404)

    def get_quality(self, name: str) -> QualityReport:
        if name not in self.quality:
            self.quality[name] = check_quality(self.con, self.get_profile(name))
        return self.quality[name]

    def query(self, sql: str, max_rows: int | None = None) -> TableResult:
        return run_select(
            self.con, sql, self.table_names(), max_rows or self.settings.max_result_rows, self.settings.sql_timeout_seconds
        )

    def preview(self, name: str, limit: int = 50) -> TableResult:
        self.get_profile(name)
        return self.query(f"SELECT * FROM {quote(name)} LIMIT {int(limit)}")

    def parquet_path(self, name: str) -> Path:
        self.get_profile(name)
        folder = self.directory / f"parquet_{name}"
        path = folder / "data.parquet"
        if not path.exists():
            folder.mkdir(parents=True, exist_ok=True)
            self.con.execute(f"COPY {quote(name)} TO '{path.as_posix()}' (FORMAT PARQUET)")
        return path

    def add_relationship(self, left: tuple[str, str], right: tuple[str, str]) -> Relationship:
        for table, column in (left, right):
            self.get_column(table, column)
        relationship = measure_relationship(self.con, left, right, source="user")
        self.relationships = [
            r for r in self.relationships
            if (r.left_table, r.left_column, r.right_table, r.right_column) != (*left, *right)
        ]
        self.relationships.append(relationship)
        self.save()
        return relationship

    def relationships_between(self, a: str, b: str) -> list[Relationship]:
        return [r for r in self.relationships if {r.left_table, r.right_table} == {a, b}]

    def close(self, delete: bool = True) -> None:
        self.con.close()
        if delete:
            shutil.rmtree(self.directory, ignore_errors=True)
