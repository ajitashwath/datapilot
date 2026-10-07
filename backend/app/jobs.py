import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.errors import UserError
from app.logging_setup import log_event
from app.metrics import metrics

MAX_JOBS_KEPT = 200


@dataclass
class Job:
    id: str
    session_id: str
    kind: str
    status: str = "queued"
    message: str = ""
    datasets: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None


class JobRunner:
    def __init__(self, workers: int = 2):
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="datapilot-job")
        self.jobs: dict[str, Job] = {}
        self.guard = threading.Lock()

    def submit(self, session_id: str, kind: str, work: Callable[[], list[str]]) -> Job:
        job = Job(id=uuid.uuid4().hex, session_id=session_id, kind=kind)
        with self.guard:
            self.jobs[job.id] = job
            self.prune()
        self.pool.submit(self.execute, job, work)
        return job

    def execute(self, job: Job, work: Callable[[], list[str]]) -> None:
        job.status = "running"
        started = time.perf_counter()
        try:
            job.datasets = work()
            job.status = "done"
            job.message = f"Imported {len(job.datasets)} dataset{'s' if len(job.datasets) != 1 else ''}."
        except UserError as exc:
            job.status, job.message = "error", exc.message
        except Exception:
            log_event("job_failed", kind=job.kind, exc_info=True)
            job.status, job.message = "error", "The import failed unexpectedly. Check the source and try again."
        job.finished_at = time.time()
        metrics.inc("datapilot_jobs_total", kind=job.kind, status=job.status)
        log_event("job_finished", kind=job.kind, status=job.status, duration_ms=round((time.perf_counter() - started) * 1000, 1))

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def prune(self) -> None:
        if len(self.jobs) <= MAX_JOBS_KEPT:
            return
        finished = sorted((j for j in self.jobs.values() if j.finished_at), key=lambda j: j.finished_at)
        for job in finished[: len(self.jobs) - MAX_JOBS_KEPT]:
            del self.jobs[job.id]

    def shutdown(self) -> None:
        self.pool.shutdown(wait=False, cancel_futures=True)
