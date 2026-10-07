from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = ""
    llm_max_tokens: int = 2048

    max_upload_mb: int = 50
    max_files_per_session: int = 10
    max_sessions: int = 50
    session_ttl_minutes: int = 120

    max_result_rows: int = 200
    sql_timeout_seconds: float = 15.0
    python_timeout_seconds: float = 10.0
    python_memory_mb: int = 2048
    duckdb_memory_limit: str = "1GB"
    max_agent_steps: int = 8
    history_turns: int = 10

    secret_key: str = ""
    access_token: str = ""
    trust_proxy: bool = False
    chat_per_minute: int = 12
    upload_per_minute: int = 20
    session_create_per_hour: int = 30
    server_key_turn_limit: int = 100
    sandbox_mode: str = "subprocess"

    cors_origins: str = "http://localhost:3000"
    sample_data_dir: str = str(ROOT_DIR / "data")
    upload_root: str = ""
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
