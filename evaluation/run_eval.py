import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "evaluation"))

from cases import CASES, DATA_DIR, GROUNDING_CHECKS, Case, Turn
from app.agent.agent import DoneEvent, ErrorEvent, TextEvent, ToolCallEvent, ToolResultEvent, find_ungrounded_numbers, parse_numbers, run_turn
from app.agent.llm import LLMProvider, create_provider
from app.agent.tools import result_for_llm, run_tool
from app.config import Settings
from app.data.datasets import DatasetStore
from app.logging_setup import logger
from app.models import ToolResult
from app.session import Session

import tempfile


@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class TurnOutcome:
    tools_used: list[str] = field(default_factory=list)
    results: list[ToolResult] = field(default_factory=list)
    answer: str = ""
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


def make_session(settings: Settings) -> Session:
    store = DatasetStore(Path(tempfile.mkdtemp(prefix="datapilot-eval-")), settings)
    for name in ("customers", "products", "orders"):
        store.add_csv(f"{name}.csv", (DATA_DIR / f"{name}.csv").read_bytes())
    return Session(id="eval", store=store)


def run_plan(session: Session, turn: Turn) -> TurnOutcome:
    outcome = TurnOutcome()
    for tool, args in turn.plan:
        outcome.tools_used.append(tool)
        outcome.results.append(run_tool(session, tool, args))
    return outcome


def run_live(session: Session, turn: Turn, llm: LLMProvider) -> TurnOutcome:
    outcome = TurnOutcome()
    last_step_text: dict[int, str] = {}
    for event in run_turn(session, turn.question, llm):
        if isinstance(event, TextEvent):
            last_step_text[event.step] = last_step_text.get(event.step, "") + event.delta
        elif isinstance(event, ToolCallEvent):
            outcome.tools_used.append(event.name)
        elif isinstance(event, ToolResultEvent):
            outcome.results.append(event.result)
        elif isinstance(event, DoneEvent):
            outcome.warnings = event.warnings
        elif isinstance(event, ErrorEvent):
            outcome.error = event.message
    outcome.answer = last_step_text[max(last_step_text)] if last_step_text else ""
    return outcome


def fact_found(fact, text: str, tolerance: float) -> bool:
    options = fact if isinstance(fact, tuple) else (fact,)
    for option in options:
        if isinstance(option, str):
            if option.lower() in text.lower():
                return True
        else:
            if any(abs(value - option) <= max(abs(option) * tolerance, tol) for value, tol in parse_numbers(text)):
                return True
    return False


def evaluate_turn(turn: Turn, outcome: TurnOutcome, live: bool, session: Session) -> list[Check]:
    checks = []
    if outcome.error:
        return [Check("completed", False, outcome.error)]
    if turn.any_tools:
        ok = any(set(alt) <= set(outcome.tools_used) for alt in turn.any_tools)
        checks.append(Check("tool_selection", ok, f"used {outcome.tools_used}, accepted {turn.any_tools}"))
    if turn.facts:
        text = outcome.answer if live else " ".join(result_for_llm(r) for r in outcome.results)
        missing = [f for f in turn.facts if not fact_found(f, text, 0.015 if live else 1e-4)]
        checks.append(Check("correct_result", not missing, f"missing {missing}" if missing else "all expected facts present"))
    if turn.needs_sql or turn.sql_contains:
        sqls = [r.sql for r in outcome.results if r.ok and r.sql]
        joined = " ".join(sqls).upper()
        checks.append(Check("sql_valid", bool(sqls) and all(s.upper() in joined for s in turn.sql_contains), f"{len(sqls)} executed queries"))
    if turn.chart_type:
        charts = [r.chart for r in outcome.results if r.ok and r.chart]
        ok = any(c.type == turn.chart_type and len(c.data) >= turn.min_chart_points and c.title and c.x_label for c in charts)
        checks.append(Check("chart_generated", ok, f"charts: {[(c.type, len(c.data)) for c in charts]}"))
    if turn.needs_anomaly:
        found = [a for r in outcome.results for a in r.anomalies if a.is_anomaly]
        checks.append(Check("anomaly_detected", bool(found) and all(a.reason for a in found), f"{len(found)} anomalous columns"))
    if turn.expect_tool_error:
        checks.append(Check("tool_error_handled", any(not r.ok for r in outcome.results) or live, "tool rejected the request"))
        checks.append(Check("data_intact", "orders" in session.store.table_names() and session.store.get_profile("orders").rows > 7000, ""))
    if turn.expect_empty_result:
        first = next((r for r in outcome.results if r.table), None)
        empty = first is not None and (not first.table.rows or first.table.rows[0][0] is None)
        checks.append(Check("no_fabrication", empty or live, "query returned no value"))
    if live:
        checks.append(Check("grounded_numbers", not outcome.warnings, "; ".join(outcome.warnings) or "all figures found in tool output"))
        if turn.answer_any:
            hit = any(p in outcome.answer.lower() for p in turn.answer_any)
            checks.append(Check("answer_behaviour", hit, "answer acknowledges the limitation or assumption" if hit else outcome.answer[:120]))
    return checks


def run_case(case: Case, live: bool, settings: Settings, llm: LLMProvider | None) -> dict:
    session = make_session(settings)
    checks: list[Check] = []
    transcript: list[dict] = []
    try:
        for turn in case.turns:
            outcome = run_live(session, turn, llm) if live else run_plan(session, turn)
            checks.extend(evaluate_turn(turn, outcome, live, session))
            transcript.append({"question": turn.question, "tools": outcome.tools_used, "answer": outcome.answer[:600], "warnings": outcome.warnings})
    finally:
        session.store.close()
    return {
        "id": case.id, "category": case.category, "passed": all(c.passed for c in checks),
        "checks": [c.__dict__ for c in checks],
        "turns": transcript if live else [],
    }


def run_grounding_checks() -> list[dict]:
    results = []
    for label, answer, tool_texts, should_flag in GROUNDING_CHECKS:
        flagged = bool(find_ungrounded_numbers(answer, tool_texts, "question"))
        results.append({"id": f"grounding: {label}", "category": "hallucination", "passed": flagged == should_flag, "checks": []})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the DataPilot analyst against ground truth computed with pandas.")
    parser.add_argument("--mode", choices=["tools", "live"], default="tools", help="tools runs reference plans on the real tools, live also calls the LLM")
    parser.add_argument("--pause", type=float, default=0.0, help="seconds to wait between live cases")
    parser.add_argument("--only", help="comma separated case ids to run")
    parser.add_argument("--out", default=str(ROOT / "evaluation" / "results" / "latest.json"))
    args = parser.parse_args()
    logger.disabled = True
    live = args.mode == "live"
    settings = Settings()
    llm = create_provider(settings) if live else None
    wanted = set(args.only.split(",")) if args.only else None
    cases = [c for c in CASES if (live or not c.live_only) and (wanted is None or c.id in wanted)]
    results = []
    for index, case in enumerate(cases):
        if live and index and args.pause:
            time.sleep(args.pause)
        results.append(run_case(case, live, settings, llm))
    results += [] if wanted else run_grounding_checks()

    width = max(len(r["id"]) for r in results)
    for r in results:
        print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['id']:<{width}}  [{r['category']}]")
        for c in r["checks"]:
            if not c["passed"]:
                print(f"        {c['name']}: {c['detail']}")
    passed = sum(r["passed"] for r in results)
    print(f"\nmode={args.mode}  passed {passed}/{len(results)}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps({"mode": args.mode, "passed": passed, "total": len(results), "results": results}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
