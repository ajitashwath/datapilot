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

    auth_mode: str = "none"
    registration: str = "open"
    allowed_email_domain: str = ""
    token_ttl_days: int = 30
    login_per_minute: int = 10
    shared_per_minute: int = 30
    max_teams_per_user: int = 20
    schedule_min_minutes: int = 15
    max_schedules_per_session: int = 10
    schedule_runs_kept: int = 20
    max_shares_per_session: int = 20
    allow_private_connections: bool = False
    connector_max_rows: int = 1_000_000
    connector_timeout_seconds: float = 30.0
    scheduler_enabled: bool = True

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_security: str = "starttls"
    public_url: str = "http://localhost:3000"
    require_email_verification: bool = False
    reset_token_minutes: int = 60
    verify_token_hours: int = 24
    forgot_per_hour: int = 5

    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.smtp_from)

    def sessions_root(self) -> Path:
        return Path(self.upload_root) if self.upload_root else ROOT_DIR / "var" / "sessions"

    cors_origins: str = "http://localhost:3000"
    sample_data_dir: str = str(ROOT_DIR / "data")
    upload_root: str = ""
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
