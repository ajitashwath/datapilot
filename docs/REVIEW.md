# Requirements review

A strict self-review of DataPilot. Status values: **Done** (implemented and exercised by tests or a manual run), **Partial** (implemented, but part of it could not be verified in the build environment).

## Assignment requirements

| Requirement | Implementation | Status | Evidence |
| --- | --- | --- | --- |
| CSV upload, multiple files | Streamed multipart upload, per-file results, drag and drop | Done | `api/routes.py`, `Sidebar.tsx`, `test_persistence.py::test_uploads_are_streamed...` |
| Upload validation, malformed CSV | Extension, size, binary, empty, encoding, delimiter detection, rejected-row recovery | Done | `data/loader.py`, `TestCsvValidation` |
| Schema, types, missing, duplicates, cardinality, kinds | DuckDB based profiler | Done | `data/profiler.py`, `TestSchemaInference` |
| Natural language analysis executed on data | Tool loop over DuckDB and pandas | Done | `agent/agent.py`, `TestToolRouting`, evaluation |
| No invented numbers | Prompt rules plus grounding check against tool output and schema | Done | `find_ungrounded_numbers`, `TestHallucinationResistance` |
| LLM tool calling with the listed tools | 10 required tools plus `set_context_filters` | Done | `agent/tools.py` |
| Safe Python execution | AST policy, module-refusing wrappers, subprocess, timeout, rlimits and Windows job object, off switch | Done (not a hardened jail) | `data/sandbox.py`, `data/sandbox_runner.py`, `TestPythonSandbox`, `test_python_switch.py` |
| SQL generation and execution on DuckDB | Parse tree validator, single SELECT, timeout, row cap | Done | `data/engine.py`, `TestSqlExecution` |
| Charts, anomalies, quality, overview, multi-file, context | See the feature list in the README | Done | `tests/`, `frontend/src` |
| Streaming | SSE with text, tool call and tool result events | Done | `api/routes.py::event_stream` |
| Error handling, observability | Typed user errors, sanitised 500s, JSON logs, Prometheus metrics | Done | `errors.py`, `main.py`, `metrics.py` |
| Evaluation suite | 18 cases with pandas ground truth plus 4 grounding checks, two modes | Partial (live run incomplete, see below) | `evaluation/` |
| Tests | 168 backend, 10 frontend, runnable offline, green on Windows and Linux | Done | `tests/`, `frontend/src/lib/*.test.ts` |
| Docker | Dockerfiles, compose with volume and limits, CI build job | Partial (images never built here) | `docker-compose.yml`, `.github/workflows/ci.yml` |
| README, diagram, sample data, polished UI | Complete | Done | `README.md`, `data/`, `docs/screenshots` |

## Productionisation work

| Area | What was done | Status | Evidence |
| --- | --- | --- | --- |
| Sandbox isolation | Runtime module guard (closed a real `pd.compat.os` escape), `__import__` handling, Windows job object memory limit, Linux rlimits, `SANDBOX_MODE=off` | Done | `test_data_layer.py` sandbox tests, run on Windows and Ubuntu (WSL) |
| Authentication | Optional bearer token, constant time compare, login screen | Done (shared token, not per-user) | `api/security.py`, `test_security.py`, browser run |
| Rate limits and quotas | Per IP sliding windows for chat, upload, session creation; shared key question quota | Done | `limits.py`, `test_security.py` |
| API key handling | Fernet in memory, never returned, never logged, never persisted | Done | `secrets_box.py`, `test_persistence.py::test_api_keys_are_never_written_to_disk` |
| Persistence | Per-session DuckDB file, metadata, transcript, restore on start, expiry cleanup | Done | `test_persistence.py`, real restart in the browser |
| Large files | Streaming upload, streaming re-encoding, DuckDB disk spilling | Done | `loader.py`, 400k row stress run |
| Queue and storage layer | Deliberately not added (synchronous processing is fast enough); files on a volume are the storage layer | Declined | `docs/DEPLOY.md` |
| Live verification | Gemini run on 18 cases: 12 passed, 4 blocked by the free tier quota (20 requests per day), 2 failed | Partial | README, Known limitations |
| Export and saved analyses | CSV export, Markdown report export, saved transcript restored on reload, chart type switch | Done | `export.test.ts`, browser run |
| Accounts, teams, scheduling, connectors, shared dashboards | Not built; separate products | Declined | README, Known limitations |
| Responsive and accessible UI | Phone layout with drawer, keyboard focus, labels, live regions; axe-core (WCAG 2.1 A and AA) reports no violations on chat, all explorer tabs and settings at phone and desktop widths | Done | browser audits |
| Metrics and alerting | `/api/metrics` counters, example alert rules | Done (no alert manager bundled) | `metrics.py`, `docs/DEPLOY.md` |
| CI | GitHub Actions: backend tests and evaluation, frontend typecheck, tests and build, dependency audits, Docker build and health check | Partial (workflow not executed here; each command was run locally) | `.github/workflows/ci.yml` |
| Dependency pinning and scanning | `requirements.lock`, `pip-audit` clean, `npm audit --omit=dev` clean; vulnerable starlette, python-multipart, cryptography, anyio, idna, python-dotenv and next/postcss upgraded | Done | `backend/requirements.lock` |
| Deploy setup | Hardened compose file, volume, health checks, deployment guide | Done | `docs/DEPLOY.md` |

## Still open

- Build and run the Docker images, and run the CI workflow on GitHub.
- Re-run the live evaluation when the Gemini quota resets or with a paid key, and investigate `top_five_customers` and the tightened chart prompt.
- Run OpenAI and Anthropic live.
- Move `execute_python` into a network-less sandbox container if it must stay enabled for untrusted users.
- Per-user accounts and persistence beyond a single node if this becomes a multi-tenant service.
