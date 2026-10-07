# Deployment guide

DataPilot is one FastAPI process plus one Next.js process. Sessions and uploaded data live on a local disk volume, so there is no database or queue to run.

## Quick start with Docker

```bash
cp .env.example .env
```

Edit `.env`:

| Variable | Why you want it in production |
| --- | --- |
| `ACCESS_TOKEN` | Shared access token login for a single team. Without it, and without accounts, anyone who can reach the server can use it. |
| `AUTH_MODE=accounts` | Per-user accounts, workspaces, teams and roles. Pair with `REGISTRATION=closed` or `ALLOWED_EMAIL_DOMAIN=yourcompany.com` to control who can sign up. |
| `SECRET_KEY` | A Fernet key (`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`). Used to encrypt API keys held in memory and two-factor secrets. If unset, a random key is generated at each start and two-factor sign-in is unavailable. |
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

## Accounts, teams and sharing

- With `AUTH_MODE=accounts` the first person to register is just a normal user: there is no built-in super admin. Create the first accounts, then set `REGISTRATION=closed` to stop further sign-ups.
- Passwords are hashed with scrypt and sign-in tokens are stored hashed. Accounts, teams, share links and schedules live in `app.db` next to the session folders (SQLite, WAL mode).
- Workspaces owned by a user never expire. Anonymous workspaces expire after `SESSION_TTL_MINUTES` unless they have an active schedule. Set it to `0` to disable expiry.
- Public share links expose a snapshot of a conversation (tables, SQL, charts) to anyone with the URL until revoked. Put the site behind your normal access controls if links must stay inside your network, or disable sharing by not giving users the owner role.

## Single sign-on (OpenID Connect)

Accounts mode can sign users in through any standard OpenID Connect provider (Google, Microsoft Entra, Okta, Keycloak and similar). Register DataPilot with the provider as a web application, set the redirect address to `PUBLIC_URL` followed by `/sso` (for example `https://data.example.com/sso`), then set:

| Variable | Meaning |
| --- | --- |
| `OIDC_ISSUER` | The provider's issuer address, which must serve `/.well-known/openid-configuration` |
| `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` | From the provider's app registration |
| `OIDC_NAME` | Label for the button (default "single sign-on") |
| `OIDC_SCOPES` | Default `openid email profile` |

The flow is the authorization code flow with PKCE, a single-use state and a nonce. The identity token must be RS256 signed by a key from the provider's key set, with the right issuer, audience and expiry, and the provider must report the email as verified. Accounts are matched by email: an existing password account with the same email is signed in to, and a new account is created if registration is open. `ALLOWED_EMAIL_DOMAIN` still applies. Signing in through the provider counts as the second factor, so the local two-factor prompt is skipped. The provider must use https unless `ALLOW_PRIVATE_CONNECTIONS=true`.

## Two-factor sign-in

Accounts mode offers authenticator app codes (TOTP, any standard app). Set a stable `SECRET_KEY`; without one the option is hidden, because the stored secrets could not be read after a restart. Users turn it on from the 2FA button, which shows a QR code and 10 single-use recovery codes. Sign-in then asks for a code after the password, and a password reset does not skip it.

If someone loses both their phone and their recovery codes, an administrator can turn it off from the server:

```bash
cd backend && python -m app.admin disable-2fa user@example.com
```

That also signs the account out everywhere. Run it with the same environment (`UPLOAD_ROOT`) as the server.

## Email (optional)

Set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` and `PUBLIC_URL` (the address people use to reach the site, because it goes into every emailed link). Leave `SMTP_SECURITY=starttls` for port 587, or `ssl` for port 465. With email on you get forgot-password, change-password notices, optional email confirmation (`REQUIRE_EMAIL_VERIFICATION=true`) and email notifications for scheduled queries. Without it those features stay hidden and sign-up works as before.

- Existing accounts are treated as confirmed when you switch confirmation on.
- Use a dedicated sending address with SPF and DKIM set up, or reset emails will land in spam.
- Delivery failures are logged (`email_failed`) and counted in `datapilot_emails_total{status="failed"}`; the request that triggered the email still succeeds so the form never reveals whether an address exists.

## Webhook notifications

A schedule can also post to a webhook address, using the same "only on failure" or "after every run" setting as email. It works without email being set up. The body is a small JSON summary (schedule name, workspace id, ok, row count, error text) and never contains query results. Each request carries `X-DataPilot-Signature: sha256=<hex>`, the HMAC SHA-256 of the raw body with a per-schedule secret that is shown once when the schedule is created.

Addresses must be https, without embedded credentials, and resolve to public addresses (checked again on every send, with the connection pinned to the checked address). Redirects are not followed, and the delivery outcome is written to the run's note. Set `ALLOW_PRIVATE_CONNECTIONS=true` only on a trusted network, since it also allows plain http and private targets. The address itself is never shown back in the interface, only its host, because many services put a secret in the path. The signing secret is stored in the app database as plain text so it can be used to sign.

## Connectors and schedules

- Imports from links, SQLite files and Postgres run as background jobs (two workers). All outbound connections must resolve to public addresses unless `ALLOW_PRIVATE_CONNECTIONS=true`, which you should only use on a trusted development network.
- If your Postgres is on a private network, keep the default and import through a public read replica or a tunnel you control, or accept the risk and enable private connections on a dedicated deployment.
- The scheduler is a thread inside the backend process (checks every 30 seconds). Disable it with `SCHEDULER_ENABLED=false` on instances that should not run jobs. Schedules are SQL only and store their last 20 results.

## Testing the Postgres connector

`bash scripts/run_postgres_tests.sh` starts a throwaway PostgreSQL (from the `pgserver` pip package) on a local port and runs `tests/test_postgres_integration.py` against it. Without a server those tests skip. Set `TEST_PG_HOST`, `TEST_PG_PORT`, `TEST_PG_USER` and `TEST_PG_PASSWORD` to use your own instance (the account needs permission to create databases and roles).

## Persistence and cleanup

- Datasets, profiles, filters, conversation history and the saved transcript survive restarts.
- API keys are never written to disk. Users re-enter them after a restart.
- Sessions idle longer than `SESSION_TTL_MINUTES` (default 120) are deleted together with their files.
- DuckDB spills large intermediate results to `<session folder>/spill`, so memory use is bounded by `DUCKDB_MEMORY_LIMIT` (default 1 GB).
- Back up the whole volume (session folders and `app.db`) if you want data to outlive the container. `app.db` holds accounts, teams, shares and schedules.

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
