# Deployment guide

DataPilot is one FastAPI process plus one Next.js process. Sessions and uploaded data live on a local disk volume, so there is no database or queue to run.

## Quick start with Docker

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Why you want it in production |
| --- | --- |
| `ACCESS_TOKEN` | Turns on the access token login. Without it anyone who can reach the server can use it. |
| `SECRET_KEY` | A Fernet key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Used to encrypt API keys held in memory. If unset, a random key is generated at each start. |
| `LLM_PROVIDER` and the matching `*_API_KEY` | Optional shared key. Leave empty to make every user bring their own key in Settings. |
| `SERVER_KEY_TURN_LIMIT` | Questions one session may ask on the shared key (default 100). Users who add their own key are exempt. |
| `CHAT_PER_MINUTE`, `UPLOAD_PER_MINUTE`, `SESSION_CREATE_PER_HOUR` | Per client IP rate limits (defaults 12, 20, 30). |
| `TRUST_PROXY=true` | Only when running behind a reverse proxy that sets `X-Forwarded-For`, so limits apply per real client. |
| `SANDBOX_MODE=off` | Disables the `execute_python` tool entirely and leaves SQL only. Recommended unless you need Python analysis. |
| `CORS_ORIGINS` | The public URL of the frontend. |

```bash
docker compose up --build -d
```

- Frontend: http://localhost:3000, API: http://localhost:8000
- Data volume: `datapilot-data` mounted at `/var/lib/datapilot` (one folder per session with a DuckDB file).
- The backend container is non-root, read-only, drops all capabilities and is limited to 3 GB and 256 processes.

Set `NEXT_PUBLIC_API_URL` as a build arg in `docker-compose.yml` to the public API URL before building the frontend image, because Next.js bakes it into the bundle.

## Behind HTTPS

Put a reverse proxy (Caddy, nginx or a cloud load balancer) in front of both services. Requirements:

- Terminate TLS and forward `X-Forwarded-For`, then set `TRUST_PROXY=true`.
- Do not buffer the chat endpoint: responses are server-sent events. The API already sends `X-Accel-Buffering: no`.
- Route `/api/*` to the backend and everything else to the frontend, or use two hostnames and set `CORS_ORIGINS` accordingly.

## Run exactly one backend worker

DuckDB files are single writer and the rate limiter and session map are in process memory. The Dockerfile already starts uvicorn with `--workers 1`. Scale vertically, or shard users across several independent deployments.

## Persistence and cleanup

- Datasets, profiles, filters, conversation history and the saved transcript survive restarts.
- API keys are never written to disk. Users re-enter them after a restart.
- Sessions idle longer than `SESSION_TTL_MINUTES` (default 120) are deleted together with their files.
- DuckDB spills large intermediate results to `<session folder>/spill`, so memory use is bounded by `DUCKDB_MEMORY_LIMIT` (default 1 GB).
- Back up the volume if you want session data to outlive the container.

## Monitoring

`GET /api/metrics` returns Prometheus text (protected by the access token when one is set). Useful series:

| Metric | Meaning |
| --- | --- |
| `datapilot_http_requests_total{method,path,status}` | Traffic and error rate. Alert on a rising share of `5xx`. |
| `datapilot_http_request_seconds_sum{path}` | Total request time per route. |
| `datapilot_chat_turns_total{outcome}` | Finished questions. Alert on `outcome="error"` growth. |
| `datapilot_llm_requests_total{provider}` and `datapilot_llm_seconds_sum{provider}` | LLM usage and latency. |
| `datapilot_tool_calls_total{tool,ok}` | Which tools run and how often they fail. |
| `datapilot_rate_limited_total{scope}` | Abuse and misconfigured clients. |
| `datapilot_sessions_active` | Current in-memory sessions. |

Logs are JSON lines on stdout with `request_id` and `session_id` on every line. Ship them with your platform's log driver.

Example Prometheus alert rules:

```yaml
- alert: DataPilotErrorsHigh
  expr: sum(rate(datapilot_http_requests_total{status=~"5.."}[5m])) > 0.1
  for: 10m
- alert: DataPilotChatFailures
  expr: sum(rate(datapilot_chat_turns_total{outcome="error"}[10m])) > 0.2
  for: 10m
```

## Dependency hygiene

- Backend versions are pinned in `backend/requirements.lock`; `backend/requirements.txt` holds the minimum versions. Regenerate the lock in a clean virtualenv after changing the minimums.
- CI runs `pip-audit` against the lock file and `npm audit --omit=dev` for the frontend on every push.
- Known and accepted: `npm audit` still reports dev-only tooling advisories (the test runner and the Tailwind 3 glob chain). They are not shipped in the production image.
