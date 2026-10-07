from app.agent.prompts import build_system_prompt
from app.agent.tools import run_tool, tool_specs
from fakes import ScriptedLLM, call, say
from app.agent.agent import ToolResultEvent, run_turn


def test_python_tool_is_listed_by_default(session):
    assert "execute_python" in {s.name for s in tool_specs()}
    assert run_tool(session, "execute_python", {"code": "result = 1 + 1"}).ok


def test_switch_off_removes_and_blocks_the_python_tool(session):
    session.store.settings.sandbox_mode = "off"
    assert "execute_python" not in {s.name for s in tool_specs(python_enabled=False)}
    blocked = run_tool(session, "execute_python", {"code": "result = 1"})
    assert not blocked.ok and "disabled" in blocked.error
    assert "Python execution is disabled" in build_system_prompt(session)


def test_agent_does_not_offer_python_when_off(session):
    session.store.settings.sandbox_mode = "off"
    llm = ScriptedLLM(call("execute_python", code="result = 1"), say("I could not run Python."))
    events = list(run_turn(session, "compute something", llm))
    result = [e for e in events if isinstance(e, ToolResultEvent)][0].result
    assert not result.ok and "disabled" in result.error
