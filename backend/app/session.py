import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.agent.llm import LLMConfig, Message
from app.config import Settings
from app.data.datasets import DatasetStore
from app.errors import UserError


@dataclass
class AnalysisRecord:
    question: str
    answer: str
    tools: list[str]
    result_preview: str


@dataclass
class Session:
    id: str
    store: DatasetStore
    history: list[Message] = field(default_factory=list)
    records: list[AnalysisRecord] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)
    active_dataset: str | None = None
    llm: LLMConfig | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_used: float = field(default_factory=time.time)


class SessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions: dict[str, Session] = {}
        self.guard = threading.Lock()
        self.root = Path(settings.upload_root) if settings.upload_root else Path(tempfile.gettempdir()) / "datapilot"

    def create(self) -> Session:
        with self.guard:
            self.expire_old()
            if len(self.sessions) >= self.settings.max_sessions:
                oldest = min(self.sessions.values(), key=lambda s: s.last_used)
                self.sessions.pop(oldest.id).store.close()
            session_id = uuid.uuid4().hex
            store = DatasetStore(self.root / session_id, self.settings)
            session = Session(id=session_id, store=store)
            self.sessions[session_id] = session
            return session

    def get(self, session_id: str) -> Session:
        session = self.sessions.get(session_id)
        if session is None:
            raise UserError("This session has expired or does not exist. Please start a new one.", "session_not_found", 404)
        session.last_used = time.time()
        return session

    def delete(self, session_id: str) -> None:
        with self.guard:
            session = self.sessions.pop(session_id, None)
        if session:
            session.store.close()

    def expire_old(self) -> None:
        cutoff = time.time() - self.settings.session_ttl_minutes * 60
        for session_id in [s.id for s in self.sessions.values() if s.last_used < cutoff and not s.lock.locked()]:
            self.sessions.pop(session_id).store.close()
