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
| Tests | 240 backend, 16 frontend, runnable offline, green on Windows and Linux | Done | `tests/`, `frontend/src/lib/*.test.ts` |
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
| Live verification | Gemini run on 18 cases: 12 passed, 4 blocked by the free tier quota (20 requests per day), 2 failed | Partial | README, Known limitations |
| Export and saved analyses | CSV export, Markdown report export, saved transcript restored on reload, chart type switch | Done | `export.test.ts`, browser run |
| Accounts and teams | `AUTH_MODE=accounts`: scrypt passwords, hashed tokens, throttled sign-in, private workspaces (404 not 403), teams with admin, member and viewer roles, read-only enforcement | Done (no email verification, SSO or password reset) | `accounts.py`, `api/deps.py`, `test_accounts.py`, two-user browser run |
| Shareable analyses | Immutable public snapshot links with revoke, noindex, rate limit, public read-only page | Done (snapshots, not live dashboards) | `sharing.py`, `app/share/[token]`, `test_sharing_schedules.py`, signed-out browser run |
| Scheduling | Saved SQL on an interval, run now, pause, history, optional refresh of linked data, scheduler thread, expiry exemption | Done (SQL only, no notifications) | `schedules.py`, `test_sharing_schedules.py`, browser run |
| Connectors | CSV link and Google Sheets with refresh, SQLite file, Postgres, SSRF protection with DNS pinning and redirect checks | Done (Postgres verified against a fake driver only) | `connectors.py`, `test_connectors.py`, browser run |
| Job queue | In-process job runner with status polling, used for imports and refreshes | Done (single node) | `jobs.py`, `connector_routes.py` |
| Responsive and accessible UI | Phone layout with drawer, keyboard focus, labels, live regions; axe-core (WCAG 2.1 A and AA) reports no violations on chat, all explorer tabs and settings at phone and desktop widths | Done | browser audits |
| Metrics and alerting | `/api/metrics` counters, example alert rules | Done (no alert manager bundled) | `metrics.py`, `docs/DEPLOY.md` |
| CI | GitHub Actions: backend tests and evaluation, frontend typecheck, tests and build, dependency audits, Docker build and health check | Partial (workflow not executed here; each command was run locally) | `.github/workflows/ci.yml` |
| Dependency pinning and scanning | `requirements.lock`, `pip-audit` clean, `npm audit --omit=dev` clean; vulnerable starlette, python-multipart, cryptography, anyio, idna, python-dotenv and next/postcss upgraded | Done | `backend/requirements.lock` |
| Deploy setup | Hardened compose file, volume, health checks, deployment guide | Done | `docs/DEPLOY.md` |

## Bugs found while building the new features

- Join detection crashed with a server error when two datasets were named like internal SQL aliases (for example `a.csv` and `b.csv`). Fixed with derived tables and a regression test.
- Percent-encoded file names in links (`Sales%20Q3.csv`) produced table names like `sales_20q3`. Fixed.
- A `<button>` nested inside a `<summary>` failed the axe nested-interactive rule. Moved out of the summary.
- The remembered workspace was shared between users of one browser. It is now stored per user.
- The lock file omitted `psycopg-binary`, which would have broken Postgres in the slim Docker image. The lock generator now honours extras.

## Still open

- Build and run the Docker images, and run the CI workflow on GitHub.
- Re-run the live evaluation when the Gemini quota resets or with a paid key, and investigate `top_five_customers` and the tightened chart prompt.
- Run OpenAI and Anthropic live, and run the Postgres connector against a real Postgres server.
- Move `execute_python` into a network-less sandbox container if it must stay enabled for untrusted users.
- Email verification, password reset and SSO if accounts are exposed beyond a trusted group; notifications for scheduled queries.
- A shared database and external job workers if this ever needs more than one node.
