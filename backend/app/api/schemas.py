from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from app.models import DatasetProfile, Relationship


class SessionCreated(BaseModel):
    session_id: str


class DatasetDetail(BaseModel):
    profile: DatasetProfile
    quality_score: int
    issue_count: int


class UploadError(BaseModel):
    filename: str
    message: str


class UploadResponse(BaseModel):
    datasets: list[DatasetDetail]
    errors: list[UploadError]


class LLMStatus(BaseModel):
    provider: str
    model: str


class LLMSettingsRequest(BaseModel):
    provider: Literal["gemini", "openai", "anthropic"]
    api_key: SecretStr = Field(min_length=8, max_length=400)
    model: str = Field("", max_length=80, pattern=r"^[A-Za-z0-9._:/-]*$")


class SessionState(BaseModel):
    session_id: str
    name: str
    role: str
    team_id: str | None = None
    datasets: list[DatasetDetail]
    relationships: list[Relationship]
    filters: dict[str, str]
    active_dataset: str | None
    llm: LLMStatus | None = None


class RelationshipRequest(BaseModel):
    left_table: str = Field(min_length=1, max_length=100)
    left_column: str = Field(min_length=1, max_length=200)
    right_table: str = Field(min_length=1, max_length=100)
    right_column: str = Field(min_length=1, max_length=200)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    dataset: str | None = Field(None, max_length=100)


class AppConfig(BaseModel):
    llm_configured: bool
    provider: str
    model: str
    default_models: dict[str, str]
    max_upload_mb: int
    max_files_per_session: int
    sql_timeout_seconds: float
    python_timeout_seconds: float
    max_result_rows: int
    sample_datasets: list[str]
    auth_required: bool
    auth_mode: str
    registration_open: bool
    python_enabled: bool
    schedule_min_minutes: int
    allow_private_connections: bool
    email_enabled: bool = False
    email_verification_required: bool = False
    two_factor_available: bool = False
    sso_name: str | None = None
