from pathlib import Path

import pytest

from app.config import Settings
from app.data.datasets import DatasetStore
from app.session import Session

DATA_DIR = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        llm_provider="anthropic", anthropic_api_key="test-key", upload_root=str(tmp_path / "uploads"), sample_data_dir=str(DATA_DIR),
        python_timeout_seconds=5, sql_timeout_seconds=5, max_upload_mb=2,
    )


@pytest.fixture
def store(settings, tmp_path) -> DatasetStore:
    store = DatasetStore(tmp_path / "store", settings)
    for name in ("customers", "products", "orders"):
        store.add_csv(f"{name}.csv", (DATA_DIR / f"{name}.csv").read_bytes())
    yield store
    store.close()


@pytest.fixture
def session(store) -> Session:
    return Session(id="test-session", store=store)


@pytest.fixture
def empty_store(settings, tmp_path) -> DatasetStore:
    store = DatasetStore(tmp_path / "empty", settings)
    yield store
    store.close()
