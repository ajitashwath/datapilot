import pandas as pd
import pytest

from app.agent.agent import DoneEvent, ErrorEvent, TextEvent, ToolCallEvent, ToolResultEvent, find_ungrounded_numbers, run_turn
from app.agent.llm import LLMError
from app.agent.tools import TOOLS, TOOLS_BY_NAME, result_for_llm, run_tool, tool_specs
from conftest import DATA_DIR
from fakes import ScriptedLLM, call, failing_llm, say


def collect(session, question, llm):
    return list(run_turn(session, question, llm))


def of_type(events, kind):
    return [e for e in events if isinstance(e, kind)]


class TestToolRouting:
    def test_sql_tool_call_then_grounded_answer(self, session):
        truth = pd.read_csv(DATA_DIR / "orders.csv").groupby("region")["revenue"].sum().sort_values(ascending=False)
        top, total = truth.index[0], truth.iloc[0]
        llm = ScriptedLLM(
            call("execute_sql", query="SELECT region, sum(revenue) AS total FROM orders GROUP BY 1 ORDER BY 2 DESC"),
            say(f"{top} generated the highest revenue at {total:,.2f}."),
        )
        events = collect(session, "Which region generated the highest revenue?", llm)
        calls, results = of_type(events, ToolCallEvent), of_type(events, ToolResultEvent)
        assert [c.name for c in calls] == ["execute_sql"]
        assert results[0].result.ok and results[0].result.sql.startswith("SELECT region")
        assert results[0].result.table.rows[0][0] == top
        done = of_type(events, DoneEvent)[0]
        assert done.tools_used == ["execute_sql"] and done.warnings == []

    def test_text_is_streamed_in_deltas(self, session):
        llm = ScriptedLLM(say("Hello ") + say("there"))
        events = collect(session, "hi", llm)
        assert [e.delta for e in of_type(events, TextEvent)] == ["Hello ", "there"]

    def test_chart_tool_returns_data_from_query(self, session):
        llm = ScriptedLLM(
            call(
                "create_visualization", chart_type="bar", title="Revenue by region", x="region", y=["total"],
                sql="SELECT region, sum(revenue) AS total FROM orders GROUP BY 1 ORDER BY 2 DESC",
            ),
            say("Here is the chart."),
        )
        result = of_type(collect(session, "chart revenue by region", llm), ToolResultEvent)[0].result
        assert result.ok and result.chart.type == "bar" and len(result.chart.data) == 5

    def test_multi_step_flow_inspects_then_queries(self, session):
        llm = ScriptedLLM(
            call("get_schema"),
            call("execute_sql", query="SELECT count(*) AS n FROM orders"),
            say("There are 7,044 orders."),
        )
        events = collect(session, "How many orders are there?", llm)
        assert [c.name for c in of_type(events, ToolCallEvent)] == ["get_schema", "execute_sql"]
        assert of_type(events, DoneEvent)[0].warnings == []

    def test_parallel_tool_calls_in_one_turn(self, session):
        both = call("get_schema", "a") + call("data_quality_check", "b", dataset="orders")
        events = collect(session, "overview", ScriptedLLM(both, say("Done.")))
        assert [r.id for r in of_type(events, ToolResultEvent)] == ["a", "b"]


class TestMalformedToolCalls:
    def test_unknown_tool_is_reported_to_the_model(self, session):
        llm = ScriptedLLM(call("drop_database"), say("I could not do that."))
        events = collect(session, "do something", llm)
        result = of_type(events, ToolResultEvent)[0].result
        assert not result.ok and "Unknown tool" in result.error
        assert isinstance(events[-1], DoneEvent)

    def test_invalid_arguments_are_reported_and_model_can_retry(self, session):
        llm = ScriptedLLM(
            call("execute_sql", "c1", wrong_field="x"),
            call("execute_sql", "c2", query="SELECT 1 AS one"),
            say("Retried."),
        )
        events = collect(session, "q", llm)
        results = of_type(events, ToolResultEvent)
        assert not results[0].result.ok and "Invalid arguments" in results[0].result.error
        assert results[1].result.ok
        second_request_messages = llm.requests[1][1]
        assert "Invalid arguments" in second_request_messages[-1].tool_results[0].content

    def test_non_dict_tool_input_does_not_crash(self, session):
        result = run_tool(session, "execute_sql", "not a dict")
        assert not result.ok

    def test_failing_sql_returns_error_not_exception(self, session):
        result = run_tool(session, "execute_sql", {"query": "SELECT * FROM missing"})
        assert not result.ok and "Unknown table" in result.error

    def test_unexpected_exception_is_sanitised(self, session, monkeypatch):
        def boom(*args, **kwargs):
            raise RuntimeError("secret internal path /srv/app/x.py")

        monkeypatch.setattr(TOOLS_BY_NAME["get_schema"], "handler", boom)
        result = run_tool(session, "get_schema", {})
        assert not result.ok and "secret" not in result.error

    def test_tools_have_valid_json_schemas(self):
        specs = tool_specs()
        assert len(specs) == len(TOOLS) >= 10
        required = {"inspect_dataset", "get_schema", "get_column_statistics", "execute_python", "execute_sql",
                    "create_visualization", "detect_anomalies", "data_quality_check", "compare_datasets", "generate_summary"}
        assert required <= {s.name for s in specs}
        assert all(s.input_schema.get("type") == "object" for s in specs)


class TestConversationContext:
    def test_filters_and_history_flow_into_next_turn(self, session):
        first = ScriptedLLM(
            call("set_context_filters", filters={"region": "North America"}),
            say("North America has the highest revenue."),
        )
        collect(session, "Which region has the highest revenue?", first)
        assert session.filters == {"region": "North America"}

        second = ScriptedLLM(say("Here is its trend."))
        collect(session, "Show me its monthly trend", second)
        system, messages = second.requests[0]
        assert "region = North America" in system
        assert "Which region has the highest revenue?" in system
        assert messages[0].text == "Which region has the highest revenue?"
        assert messages[-1].text == "Show me its monthly trend"

    def test_previous_tool_results_stay_in_history(self, session):
        collect(session, "q1", ScriptedLLM(call("execute_sql", query="SELECT 42 AS answer"), say("It is 42.")))
        second = ScriptedLLM(say("ok"))
        collect(session, "and now?", second)
        history = second.requests[0][1]
        assert any(m.role == "tool" and "42" in m.tool_results[0].content for m in history)

    def test_records_capture_question_tools_and_preview(self, session):
        collect(session, "q", ScriptedLLM(call("execute_sql", query="SELECT 7 AS seven"), say("Seven.")))
        record = session.records[-1]
        assert record.question == "q" and record.tools == ["execute_sql"] and "seven" in record.result_preview

    def test_history_is_trimmed_to_configured_turns(self, session):
        session.store.settings.history_turns = 2
        for i in range(4):
            collect(session, f"question {i}", ScriptedLLM(say(f"answer {i}")))
        assert [m.text for m in session.history if m.role == "user"] == ["question 2", "question 3"]

    def test_filters_can_be_replaced_and_cleared(self, session):
        run_tool(session, "set_context_filters", {"filters": {"a": "1"}})
        run_tool(session, "set_context_filters", {"filters": {"b": "2"}})
        assert session.filters == {"a": "1", "b": "2"}
        run_tool(session, "set_context_filters", {"filters": {}, "replace": True})
        assert session.filters == {}

    def test_dataset_selection_is_in_system_prompt(self, session):
        session.active_dataset = "orders"
        llm = ScriptedLLM(say("hi"))
        collect(session, "hello", llm)
        assert 'currently has "orders" selected' in llm.requests[0][0]

    def test_schema_not_data_is_sent_to_llm(self, session):
        llm = ScriptedLLM(say("hi"))
        collect(session, "hello", llm)
        system = llm.requests[0][0]
        assert 'Table "orders"' in system and len(system) < 12000
        assert "100751" not in system


class TestFailureHandling:
    def test_llm_failure_yields_error_and_keeps_history_clean(self, session):
        events = collect(session, "q", failing_llm("The LLM provider is down."))
        assert isinstance(events[-1], ErrorEvent) and "down" in events[-1].message
        assert session.history == [] and session.records == []

    def test_llm_failure_after_tool_use(self, session):
        llm = ScriptedLLM(call("get_schema"), LLMError("Rate limited."))
        events = collect(session, "q", llm)
        assert isinstance(events[-1], ErrorEvent)
        assert session.history == []

    def test_step_limit_stops_runaway_loops(self, session):
        session.store.settings.max_agent_steps = 3
        llm = ScriptedLLM(*[call("get_schema", f"c{i}") for i in range(3)])
        events = collect(session, "q", llm)
        assert "maximum number of analysis steps" in "".join(e.delta for e in of_type(events, TextEvent))
        assert isinstance(events[-1], DoneEvent)

    def test_failed_tool_does_not_abort_turn(self, session):
        llm = ScriptedLLM(call("execute_sql", query="DROP TABLE orders"), say("That query is not allowed."))
        events = collect(session, "drop it", llm)
        assert not of_type(events, ToolResultEvent)[0].result.ok
        assert "orders" in session.store.table_names()
        assert isinstance(events[-1], DoneEvent)


class TestHallucinationResistance:
    def test_invented_number_is_flagged(self, session):
        llm = ScriptedLLM(call("execute_sql", query="SELECT 1250 AS total"), say("Revenue was 9,876,543 last year."))
        done = of_type(collect(session, "revenue?", llm), DoneEvent)[0]
        assert done.warnings and "9,876,543" in done.warnings[0]

    def test_numbers_from_the_schema_context_are_not_flagged(self, session):
        done = of_type(collect(session, "how many orders?", ScriptedLLM(say("The data holds 7,044 orders and ends on 2024-12-31."))), DoneEvent)[0]
        assert done.warnings == []

    def test_numbers_without_any_tool_call_are_flagged(self, session):
        done = of_type(collect(session, "revenue?", ScriptedLLM(say("Revenue was 1,234,567."))), DoneEvent)[0]
        assert done.warnings

    def test_tool_numbers_are_accepted_in_rounded_forms(self):
        tool = ['{"data": {"rows": [["NA", 1238500.5], ["EU", 740.25]]}}']
        assert find_ungrounded_numbers("North America made $1.24M and Europe 740.25.", tool, "q") == []
        assert find_ungrounded_numbers("About 1,238,501 in total.", tool, "q") == []

    def test_small_numbers_years_and_question_numbers_are_ignored(self):
        assert find_ungrounded_numbers("Top 5 in 2024, among 3 groups, above 250.", [], "show values above 250") == []

    def test_result_for_llm_truncates_large_tables(self, session):
        result = run_tool(session, "execute_sql", {"query": "SELECT * FROM orders"})
        text = result_for_llm(result)
        assert len(text) <= 9100 and "more items omitted" in text or "truncated" in text
