import shutil
from pathlib import Path

import duckdb

from app.config import Settings
from app.data.engine import run_select
from app.data.loader import load_csv_table, save_upload, table_name_for, validate_upload
from app.data.profiler import profile_dataset, quote
from app.data.quality import check_quality
from app.data.relations import infer_between, measure_relationship
from app.errors import UserError
from app.models import DatasetProfile, QualityReport, Relationship, TableResult


class DatasetStore:
    def __init__(self, directory: Path, settings: Settings):
        self.directory = directory
        self.settings = settings
        self.con = duckdb.connect(":memory:")
        self.con.execute(f"SET memory_limit='{settings.duckdb_memory_limit}'")
        self.con.execute("SET threads=2")
        self.profiles: dict[str, DatasetProfile] = {}
        self.quality: dict[str, QualityReport] = {}
        self.files: dict[str, Path] = {}
        self.relationships: list[Relationship] = []

    def table_names(self) -> set[str]:
        return set(self.profiles)

    def add_csv(self, filename: str, content: bytes) -> DatasetProfile:
        if len(self.profiles) >= self.settings.max_files_per_session:
            raise UserError(f"A session can hold at most {self.settings.max_files_per_session} datasets.", "too_many_files", 422)
        content = validate_upload(filename, content, self.settings.max_upload_mb)
        name = table_name_for(filename, self.table_names())
        path = save_upload(self.directory, content)
        try:
            skipped = load_csv_table(self.con, name, path, filename)
            profile = profile_dataset(self.con, name, filename, skipped)
        except UserError:
            path.unlink(missing_ok=True)
            raise
        if profile.rows == 0 or profile.column_count == 0:
            self.con.execute(f"DROP TABLE IF EXISTS {quote(name)}")
            path.unlink(missing_ok=True)
            raise UserError(f"'{filename}' has a header but no data rows.", "empty_file", 422)
        for other in self.profiles.values():
            self.relationships.extend(infer_between(self.con, profile, other))
        self.profiles[name] = profile
        self.files[name] = path
        return profile

    def remove(self, name: str) -> None:
        self.get_profile(name)
        self.con.execute(f"DROP TABLE IF EXISTS {quote(name)}")
        del self.profiles[name]
        self.quality.pop(name, None)
        self.files.pop(name, None)
        self.relationships = [r for r in self.relationships if name not in (r.left_table, r.right_table)]
        shutil.rmtree(self.directory / f"parquet_{name}", ignore_errors=True)

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
        return relationship

    def relationships_between(self, a: str, b: str) -> list[Relationship]:
        return [r for r in self.relationships if {r.left_table, r.right_table} == {a, b}]

    def close(self) -> None:
        self.con.close()
        shutil.rmtree(self.directory, ignore_errors=True)
