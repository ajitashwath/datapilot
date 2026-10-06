from pydantic import BaseModel, Field

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


class SessionState(BaseModel):
    session_id: str
    datasets: list[DatasetDetail]
    relationships: list[Relationship]
    filters: dict[str, str]
    active_dataset: str | None


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
    model: str
    max_upload_mb: int
    max_files_per_session: int
    sql_timeout_seconds: float
    python_timeout_seconds: float
    max_result_rows: int
    sample_datasets: list[str]
