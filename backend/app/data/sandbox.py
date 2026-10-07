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
JOB_LIMIT_PROCESS_MEMORY = 0x100
JOB_LIMIT_KILL_ON_CLOSE = 0x2000
JOB_EXTENDED_LIMIT_INFORMATION = 9
PROCESS_ALL_ACCESS = 0x1F0FFF


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


def attach_windows_job(pid: int, memory_mb: int):
    import ctypes
    from ctypes import wintypes

    class IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimits), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    job = kernel32.CreateJobObjectW(None, None)
    limits = ExtendedLimits()
    limits.BasicLimitInformation.LimitFlags = JOB_LIMIT_PROCESS_MEMORY | JOB_LIMIT_KILL_ON_CLOSE
    limits.ProcessMemoryLimit = memory_mb * 1024 * 1024
    kernel32.SetInformationJobObject(job, JOB_EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits))
    process = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    kernel32.AssignProcessToJobObject(job, process)
    kernel32.CloseHandle(process)
    return lambda: kernel32.CloseHandle(job)


def run_python(code: str, tables: dict[str, Path], timeout: float, memory_mb: int, max_rows: int) -> dict:
    problem = check_code(code)
    if problem:
        raise UserError(f"The code was rejected before running: {problem}")
    payload = json.dumps({"code": code, "tables": {n: str(p) for n, p in tables.items()}, "max_rows": max_rows})
    options = {}
    if sys.platform != "win32":
        options["preexec_fn"] = limit_resources(memory_mb, int(timeout) + 1)
    started = time.perf_counter()
    release = None
    with tempfile.TemporaryDirectory() as workdir:
        process = subprocess.Popen(
            [sys.executable, "-I", str(RUNNER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=workdir, env=minimal_env(), **options,
        )
        if sys.platform == "win32":
            release = attach_windows_job(process.pid, memory_mb)
        try:
            stdout, stderr = process.communicate(payload, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise UserError(f"The Python code took longer than {timeout:.0f} seconds and was stopped.", "timeout") from exc
        finally:
            if release:
                release()
    duration = round((time.perf_counter() - started) * 1000, 1)
    stdout = stdout[:MAX_OUTPUT_BYTES]
    if RESULT_MARKER not in stdout:
        log_event("python_sandbox_crash", returncode=process.returncode, stderr=stderr[-500:], duration_ms=duration)
        raise UserError("The Python code crashed or exceeded its memory limit.")
    output = json.loads(stdout.split(RESULT_MARKER, 1)[1])
    log_event("python_executed", duration_ms=duration, ok=output["ok"])
    return jsonable(output)
