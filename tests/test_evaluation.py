import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_tools_mode_evaluation_passes(tmp_path):
    out = tmp_path / "result.json"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "evaluation" / "run_eval.py"), "--mode", "tools", "--out", str(out)],
        capture_output=True, text=True, timeout=300,
    )
    report = json.loads(out.read_text())
    failed = [r["id"] for r in report["results"] if not r["passed"]]
    assert completed.returncode == 0 and not failed, failed
    categories = {r["category"] for r in report["results"]}
    assert {"numeric", "chart", "anomaly", "sql", "hallucination", "safety", "context", "multi_file"} <= categories
