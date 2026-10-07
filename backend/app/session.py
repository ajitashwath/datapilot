import json
import shutil
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.accounts import Accounts
from app.agent.llm import LLMConfig, Message
from app.config import Settings
from app.data.datasets import DatasetStore
from app.errors import UserError
from app.logging_setup import log_event
from app.secrets_box import SecretBox

SESSION_FILE = "session.json"
MAX_TRANSCRIPT_TURNS = 50
DEFAULT_NAME = "Untitled analysis"


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
    def __init__(self, settings: Settings, accounts: Accounts):
        self.settings = settings
        self.accounts = accounts
        self.sessions: dict[str, Session] = {}
        self.guard = threading.RLock()
        self.box = SecretBox(settings.secret_key)
        self.root = settings.sessions_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def seal_llm(self, config: LLMConfig):
        return SealedLLM(config.provider, config.resolved_model(), self.box.seal(config.api_key.get_secret_value()))

    def open_llm(self, sealed: SealedLLM) -> LLMConfig:
        return LLMConfig(provider=sealed.provider, api_key=self.box.open(sealed.blob), model=sealed.model)

    def make_room(self) -> None:
        while len(self.sessions) >= self.settings.max_sessions:
            idle = [s for s in self.sessions.values() if not s.lock.locked()]
            if not idle:
                return
            self.unload(min(idle, key=lambda s: s.last_used))

    def unload(self, session: Session) -> None:
        self.save(session)
        session.store.close(delete=False)
        self.sessions.pop(session.id, None)

    def create(self, owner_id: str | None = None) -> Session:
        with self.guard:
            self.expire_old()
            self.make_room()
            session_id = uuid.uuid4().hex
            session = Session(id=session_id, store=DatasetStore(self.root / session_id, self.settings))
            self.sessions[session_id] = session
            self.accounts.register_workspace(session_id, owner_id, DEFAULT_NAME)
            self.save(session)
            return session

    def get(self, session_id: str) -> Session:
        with self.guard:
            session = self.sessions.get(session_id)
            if session is None:
                session = self.load_folder(self.root / session_id)
            session.last_used = time.time()
            return session

    def load_folder(self, folder: Path) -> Session:
        missing = UserError("This session has expired or does not exist. Please start a new one.", "session_not_found", 404)
        session_file = folder / SESSION_FILE
        if not session_file.is_file() or self.accounts.workspace(folder.name) is None:
            raise missing
        try:
            payload = json.loads(session_file.read_text(encoding="utf-8"))
            self.make_room()
            session = Session(id=payload["id"], store=DatasetStore(folder, self.settings))
            session.filters = payload["filters"]
            session.active_dataset = payload["active_dataset"]
            session.chat_turns = payload.get("chat_turns", 0)
            session.history = [Message(**m) for m in payload["history"]]
            session.records = [AnalysisRecord(**r) for r in payload["records"]]
            session.transcript = payload["transcript"]
            session.last_used = time.time()
        except Exception as exc:
            log_event("session_restore_failed", folder=folder.name, exc_info=True)
            raise missing from exc
        self.sessions[session.id] = session
        return session

    def delete(self, session_id: str) -> None:
        with self.guard:
            session = self.sessions.pop(session_id, None)
        if session:
            session.store.close()
        else:
            shutil.rmtree(self.root / session_id, ignore_errors=True)
        self.accounts.delete_workspace(session_id)

    def expired(self, session_id: str, last_used: float) -> bool:
        ttl = self.settings.session_ttl_minutes
        if ttl <= 0 or last_used >= time.time() - ttl * 60:
            return False
        workspace = self.accounts.workspace(session_id)
        owned = workspace is not None and workspace["owner_id"] is not None
        return not owned and not self.accounts.has_schedules(session_id)

    def expire_old(self) -> None:
        for session in list(self.sessions.values()):
            if not session.lock.locked() and self.expired(session.id, session.last_used):
                self.delete(session.id)

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
        self.accounts.touch_workspace(session.id)

    def restore_all(self) -> int:
        remaining = 0
        for folder in sorted(p for p in self.root.iterdir() if p.is_dir()):
            session_file = folder / SESSION_FILE
            try:
                saved_at = json.loads(session_file.read_text(encoding="utf-8"))["saved_at"]
            except Exception:
                log_event("session_unreadable", folder=folder.name)
                continue
            if self.expired(folder.name, saved_at):
                shutil.rmtree(folder, ignore_errors=True)
                self.accounts.delete_workspace(folder.name)
                continue
            remaining += 1
        return remaining
