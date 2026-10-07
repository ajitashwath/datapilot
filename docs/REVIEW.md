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
| Tests | 253 backend (13 of them need a real Postgres and are skipped without one), 16 frontend, runnable offline, green on Windows and Linux | Done | `tests/`, `frontend/src/lib/*.test.ts` |
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
| Live verification | Gemini run on 18 cases across three models: 16 passed, 1 failing by interpretation, 1 answered correctly with a widened check | Partial | README, Known limitations |
| Export and saved analyses | CSV export, Markdown report export, saved transcript restored on reload, chart type switch | Done | `export.test.ts`, browser run |
| Accounts and teams | `AUTH_MODE=accounts`: scrypt passwords, hashed tokens, throttled sign-in, private workspaces (404 not 403), teams with admin, member and viewer roles, read-only enforcement | Done (no email verification, SSO or password reset) | `accounts.py`, `api/deps.py`, `test_accounts.py`, two-user browser run |
| Shareable analyses | Immutable public snapshot links with revoke, noindex, rate limit, public read-only page | Done (snapshots, not live dashboards) | `sharing.py`, `app/share/[token]`, `test_sharing_schedules.py`, signed-out browser run |
| Scheduling | Saved SQL on an interval, run now, pause, history, optional refresh of linked data, scheduler thread, expiry exemption | Done (SQL only, no notifications) | `schedules.py`, `test_sharing_schedules.py`, browser run |
| Connectors | CSV link and Google Sheets with refresh, SQLite file, Postgres, SSRF protection with DNS pinning and redirect checks | Done (Postgres integration-tested on a real server, TLS through a proxy) | `connectors.py`, `test_connectors.py`, `test_postgres_integration.py`, browser run |
| Account recovery and email | Optional SMTP: email confirmation, forgot and reset links, change password with session revocation, security notice emails, schedule notifications (summary only) | Done (tested against a local SMTP server and in the browser, not a real mail provider) | `mailer.py`, `accounts.py`, `test_email_flows.py`, browser run |
| Job queue | In-process job runner with status polling, used for imports and refreshes | Done (single node) | `jobs.py`, `connector_routes.py` |
| Responsive and accessible UI | Phone layout with drawer, keyboard focus, labels, live regions; axe-core (WCAG 2.1 A and AA) reports no violations on chat, all explorer tabs and settings at phone and desktop widths | Done | browser audits |
| Metrics and alerting | `/api/metrics` counters, example alert rules | Done (no alert manager bundled) | `metrics.py`, `docs/DEPLOY.md` |
| CI | GitHub Actions: backend tests and evaluation, frontend typecheck, tests and build, dependency audits, Docker build and health check | Partial (workflow not executed here; each command was run locally) | `.github/workflows/ci.yml` |
| Dependency pinning and scanning | `requirements.lock`, `pip-audit` clean, `npm audit --omit=dev` clean; vulnerable starlette, python-multipart, cryptography, anyio, idna, python-dotenv and next/postcss upgraded | Done | `backend/requirements.lock` |
| Deploy setup | Hardened compose file, volume, health checks, deployment guide | Done | `docs/DEPLOY.md` |

## Bugs found by running real models

- Gemini 3 models reject tool conversations unless the opaque `thought_signature` returned with each tool call is sent back. The provider now captures and echoes provider-specific tool call data.
- `gemini-2.5-flash-lite` answers with nothing after a tool result when several tools are declared. The agent now asks once more without tools when a model goes silent after running tools, for any provider.
- The model ranked customers by a non-unique name column and merged different customers. The schema now shows distinct counts and a rule says to group by identifiers.
- The model computed percentages itself. The rule against model arithmetic now names percentages, ratios and growth rates explicitly.
- Comparison questions were answered without a chart. The chart rule was tightened and now passes live.

## Bugs found while building the new features

- Join detection crashed with a server error when two datasets were named like internal SQL aliases (for example `a.csv` and `b.csv`). Fixed with derived tables and a regression test.
- Percent-encoded file names in links (`Sales%20Q3.csv`) produced table names like `sales_20q3`. Fixed.
- The Postgres table listing query used `NOT IN %s` with a tuple, which is invalid in psycopg 3. The fake driver could not catch this; a real server did. Fixed.
- Scheduled runs reported the stored-row cap (50) as the row count. They now report the real total.
- A `<button>` nested inside a `<summary>` failed the axe nested-interactive rule. Moved out of the summary.
- The remembered workspace was shared between users of one browser. It is now stored per user.
- The lock file omitted `psycopg-binary`, which would have broken Postgres in the slim Docker image. The lock generator now honours extras.

## Interface

The interface was redesigned around design tokens: a left rail (workspace, views, datasets, account menu), a teal accent, light and dark themes (follows the system, switchable from the account menu) and a lighter chat with a floating composer. Every screen, dialog and menu passed an axe audit in both themes, and the layout was checked at phone width.

## Still open

- Run the CI workflow on GitHub. The Docker images build and the stack runs healthy locally (non-root user, read-only filesystem, state kept on the volume, Python sandbox limits enforced), but the workflow itself has never run.
- Re-run the whole live evaluation on one model with a paid key, so every case runs on the final prompt, and re-check `underperforming_products`.
- Run OpenAI and Anthropic live, and test Postgres TLS against a server with a private CA.
- Move `execute_python` into a network-less sandbox container if it must stay enabled for untrusted users.
- SSO if accounts are exposed beyond a trusted group; a real mail provider run for the email features.
- A shared database and external job workers if this ever needs more than one node.
