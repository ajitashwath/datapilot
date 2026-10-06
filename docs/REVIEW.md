# Requirements review

A strict self-review of DataPilot against the assignment. Status values: **Done** (implemented and exercised by tests or a manual run), **Partial** (implemented, but a part could not be verified in the build environment).

| Requirement | Implementation | Status | Evidence |
| --- | --- | --- | --- |
| CSV upload, multiple files | Multipart upload, per-file results, drag and drop | Done | `api/routes.py`, `Sidebar.tsx`, `test_api.py::test_upload_multiple_files...` |
| Upload validation, malformed CSV | Extension, size, binary, empty, encoding, delimiter detection, rejected-row recovery | Done | `data/loader.py`, `test_data_layer.py::TestCsvValidation` |
| Schema, types, missing, duplicates, cardinality, kinds | DuckDB based profiler | Done | `data/profiler.py`, `TestSchemaInference` |
| Preview and compact quality summary | Preview table, schema table, score badge | Done | `DataExplorer.tsx`, `Sidebar.tsx` |
| Natural language analysis executed on data | Tool loop over DuckDB and pandas | Done | `agent/agent.py`, `test_agent.py::TestToolRouting`, evaluation tools mode |
| No invented numbers | Prompt rules plus grounding check that flags unseen figures | Done | `find_ungrounded_numbers`, `TestHallucinationResistance` |
| LLM tool calling with the listed tools | 10 required tools plus `set_context_filters` | Done | `agent/tools.py`, `test_agent.py::test_tools_have_valid_json_schemas` |
| Safe Python execution | AST policy, isolated subprocess, timeout, limits, structured result | Partial (limits untested on Linux) | `data/sandbox.py`, `data/sandbox_runner.py`, `TestPythonSandbox` |
| SQL generation and execution on DuckDB | Parse tree validator, single SELECT, timeout, row cap | Done | `data/engine.py`, `TestSqlExecution` |
| Shows SQL, result and explanation | Expandable SQL and code blocks, result table, answer text | Done | `AssistantMessage.tsx` |
| Charts: bar, line, pie, scatter, histogram | Built from executed query results, labelled axes, legends | Done | `data/charts.py`, `ChartView.tsx`, `TestVisualizationData` |
| Anomaly detection with explanation | IQR, z-score, rolling median time series, computed reasons | Done | `data/anomalies.py`, `test_anomalies.py` |
| Conversation context | History, analysis records and focus filters injected each turn | Done | `agent/prompts.py`, `TestConversationContext` |
| Multi-file analysis | Join inference, manual relationships, `compare_datasets` | Done | `data/relations.py`, `TestRelationships` |
| Data quality analysis and UI | Eight check types, score, issue list | Done | `data/quality.py`, `QualityPanel.tsx`, `TestDataQuality` |
| Dashboard and summary | Metrics, distributions, categories, missing data, suggested questions | Done | `data/overview.py`, `DataExplorer.tsx` |
| Streaming | SSE with text, tool call and tool result events | Done | `api/routes.py::event_stream`, `lib/api.ts`, `test_chat_streams_events_in_order` |
| Error handling | Typed user errors, sanitised 500s, tool and LLM failure paths | Done | `errors.py`, `main.py`, `TestFailureHandling`, `test_api.py` |
| Observability | JSON logs with request ID, session ID, tool and query timings, LLM latency | Done | `logging_setup.py`, `test_request_id_header_and_structured_logs` |
| Evaluation suite | 18 cases with pandas ground truth and 4 grounding checks, two modes | Partial (live mode needs an API key) | `evaluation/`, `tests/test_evaluation.py` |
| Tests | 127 backend tests, 4 frontend tests, all runnable offline | Done | `tests/`, `frontend/src/lib/sse.test.ts` |
| Docker | Dockerfiles and compose with a hardened backend container | Partial (compose validated, images not built) | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` |
| README and architecture diagram | Mermaid diagram and all requested sections | Done | `README.md` |
| Sample data | Customers, products and orders with planted patterns and anomalies | Done | `data/` |
| Polished UI | Dashboard layout, tool timeline, charts, empty and error states | Done | `frontend/src`, `docs/screenshots` |

## Weakest points found and what was done

1. **Skewed distributions made the overview histograms useless.** One huge order stretched every bin. Fixed by clipping overview histograms to the 1st to 99th percentile and saying how many values are hidden.
2. **Silent mis-parsing of ragged CSVs.** DuckDB's sniffer accepted a file with inconsistent rows as a single column. Fixed by detecting the delimiter first and falling back to row rejection with a reported count.
3. **Noisy join inference.** Matching column names such as `region` produced many-to-many "relationships". Fixed by requiring a key like side and ignoring many-to-many matches.
4. **Time series flagged partial periods.** The last partial week looked like a collapse. Edge periods are now excluded and the explanation says so.
5. **Empty model replies and prompt injection through cell text.** An empty reply would have poisoned the history; it is now replaced with a message. Cell values are truncated in the prompt and flagged as untrusted.

## Still open

- Run `python evaluation/run_eval.py --mode live` with a real key and tune prompts from the failures.
- Build and run the Docker images.
- Exercise the Linux sandbox limits and consider a network namespace or a dedicated sandbox container for stronger isolation.
