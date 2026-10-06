import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from app.data.engine import jsonable
from app.data.sandbox_runner import check_code
from app.errors import UserError
from app.logging_setup import log_event

RUNNER = Path(__file__).with_name("sandbox_runner.py")
RESULT_MARKER = "@@RESULT@@"
MAX_OUTPUT_BYTES = 2_000_000


def limit_resources(memory_mb: int, cpu_seconds: int):
    def apply() -> None:
        import resource

        limit = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_DATA, (limit, limit))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))

    return apply


def minimal_env() -> dict[str, str]:
    env = {"PATH": "", "PYTHONHASHSEED": "0", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"}
    if sys.platform == "win32":
        env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "C:/Windows")
    return env


def run_python(code: str, tables: dict[str, Path], timeout: float, memory_mb: int, max_rows: int) -> dict:
    problem = check_code(code)
    if problem:
        raise UserError(f"The code was rejected before running: {problem}")
    payload = json.dumps({"code": code, "tables": {n: str(p) for n, p in tables.items()}, "max_rows": max_rows})
    options = {}
    if sys.platform != "win32":
        options["preexec_fn"] = limit_resources(memory_mb, int(timeout) + 1)
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as workdir:
        try:
            completed = subprocess.run(
                [sys.executable, "-I", str(RUNNER)],
                input=payload, capture_output=True, text=True, timeout=timeout, cwd=workdir,
                env=minimal_env(), **options,
            )
        except subprocess.TimeoutExpired as exc:
            raise UserError(f"The Python code took longer than {timeout:.0f} seconds and was stopped.", "timeout") from exc
    duration = round((time.perf_counter() - started) * 1000, 1)
    stdout = completed.stdout[:MAX_OUTPUT_BYTES]
    if RESULT_MARKER not in stdout:
        log_event("python_sandbox_crash", returncode=completed.returncode, stderr=completed.stderr[-500:], duration_ms=duration)
        raise UserError("The Python code crashed or exceeded its memory limit.")
    output = json.loads(stdout.split(RESULT_MARKER, 1)[1])
    log_event("python_executed", duration_ms=duration, ok=output["ok"])
    return jsonable(output)
