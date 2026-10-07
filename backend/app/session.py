import json
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.agent.llm import LLMConfig, Message
from app.config import ROOT_DIR, Settings
from app.data.datasets import DatasetStore
from app.errors import UserError
from app.logging_setup import log_event
from app.secrets_box import SecretBox

SESSION_FILE = "session.json"
MAX_TRANSCRIPT_TURNS = 50


@dataclass
class AnalysisRecord:
    question: str
    answer: str
    tools: list[str]
    result_preview: str


@dataclass
class SealedLLM:
    provider: str
    model: str
    blob: bytes


@dataclass
class Session:
    id: str
    store: DatasetStore
    history: list[Message] = field(default_factory=list)
    records: list[AnalysisRecord] = field(default_factory=list)
    filters: dict[str, str] = field(default_factory=dict)
    transcript: list[dict] = field(default_factory=list)
    active_dataset: str | None = None
    llm: SealedLLM | None = None
    chat_turns: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)
    last_used: float = field(default_factory=time.time)


class SessionManager:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.sessions: dict[str, Session] = {}
        self.guard = threading.Lock()
        self.box = SecretBox(settings.secret_key)
        self.root = Path(settings.upload_root) if settings.upload_root else ROOT_DIR / "var" / "sessions"
        self.root.mkdir(parents=True, exist_ok=True)

    def seal_llm(self, config: LLMConfig) -> SealedLLM:
        return SealedLLM(config.provider, config.resolved_model(), self.box.seal(config.api_key.get_secret_value()))

    def open_llm(self, sealed: SealedLLM) -> LLMConfig:
        return LLMConfig(provider=sealed.provider, api_key=self.box.open(sealed.blob), model=sealed.model)

    def create(self) -> Session:
        with self.guard:
            self.expire_old()
            if len(self.sessions) >= self.settings.max_sessions:
                oldest = min(self.sessions.values(), key=lambda s: s.last_used)
                self.sessions.pop(oldest.id).store.close()
            session_id = uuid.uuid4().hex
            session = Session(id=session_id, store=DatasetStore(self.root / session_id, self.settings))
            self.sessions[session_id] = session
            self.save(session)
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

    def save(self, session: Session) -> None:
        payload = {
            "id": session.id,
            "saved_at": time.time(),
            "filters": session.filters,
            "active_dataset": session.active_dataset,
            "chat_turns": session.chat_turns,
            "history": [m.model_dump(mode="json") for m in session.history],
            "records": [asdict(r) for r in session.records],
            "transcript": session.transcript[-MAX_TRANSCRIPT_TURNS:],
        }
        target = session.store.directory / SESSION_FILE
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(target)
        session.store.save()

    def restore_all(self) -> int:
        cutoff = time.time() - self.settings.session_ttl_minutes * 60
        restored = 0
        for folder in sorted(p for p in self.root.iterdir() if p.is_dir()):
            session_file = folder / SESSION_FILE
            try:
                payload = json.loads(session_file.read_text(encoding="utf-8"))
                if payload["saved_at"] < cutoff:
                    shutil.rmtree(folder, ignore_errors=True)
                    continue
                session = Session(id=payload["id"], store=DatasetStore(folder, self.settings))
                session.filters = payload["filters"]
                session.active_dataset = payload["active_dataset"]
                session.chat_turns = payload.get("chat_turns", 0)
                session.history = [Message(**m) for m in payload["history"]]
                session.records = [AnalysisRecord(**r) for r in payload["records"]]
                session.transcript = payload["transcript"]
                session.last_used = payload["saved_at"]
                self.sessions[session.id] = session
                restored += 1
            except Exception:
                log_event("session_restore_failed", folder=folder.name, exc_info=True)
        return restored
