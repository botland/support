# Appliance Support

Hosted AI-assisted support service for OwnEdge appliances.

See [DESIGN.md](DESIGN.md) for the full architecture and implementation plan.

## Quick start (local)

```bash
cd appliance-support
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8090
```

Or with Docker:

```bash
docker compose up --build
```

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `SUPPORT_PORT` | `8090` | HTTP listen port |
| `SUPPORT_DB_PATH` | `/data/support.db` | Ticket store |
| `SUPPORT_FREE_FOR_ALL` | `true` | Stub entitlement: allow all appliances |
| `SUPPORT_DENIED_APPLIANCE_IDS` | — | Comma-separated deny list (stub billing) |
| `SUPPORT_ENTITLED_APPLIANCE_IDS` | — | Comma-separated allow list (when set, only these pass) |
| `AI_CLI_ADAPTER` | `stub` | Diagnosis adapter: `stub` (rules) or `cli` (subprocess) |
| `AI_CLI_COMMAND` | — | Required for `cli` adapter (e.g. `python3 scripts/ai_diagnose_stub.py`) |
| `AI_CLI_TIMEOUT_SEC` | `120` | Per-invocation subprocess timeout |
| `AI_CLI_USE_PROMPT_FILE` | `false` | Pass prompt via temp file (`{prompt_file}` in command) |
| `AI_PROMPT_TEMPLATE_PATH` | `prompts/diagnose.txt` | Diagnosis prompt template |
| `DIAGNOSIS_TIMEOUT_SEC` | `180` | Overall adapter call timeout (includes retries budget per attempt) |
| `DIAGNOSIS_MAX_RETRIES` | `2` | Retries on transient CLI/timeout failures |
| `DIAGNOSIS_RETRY_BACKOFF_SEC` | `2` | Backoff multiplier between retries |
| `BILLING_ADAPTER` | `stub` | Entitlement source (`stub` until billing DB is wired) |
| `CODE_ROOT_INFEREDGE_PHASE1` | auto-detect | Path to inferedge checkout for code context |
| `CODE_ROOT_APPLIANCE_CONSOLE` | auto-detect | Path to console checkout for code context |

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness |
| `GET /v1/entitlement/{appliance_id}` | Subscription preflight |
| `POST /v1/tickets` | Submit diagnostic bundle |
| `GET /v1/tickets/{id}` | Poll ticket status / diagnosis |

## Vendor workflow (Phase 4)

Optional automation after diagnosis completes:

| Variable | Default | Purpose |
|----------|---------|---------|
| `SUPPORT_TICKET_RETENTION_DAYS` | `30` | History window for `GET /v1/tickets` |
| `GITHUB_ISSUE_ENABLED` | `false` | File GitHub issues for high-confidence bugs |
| `GITHUB_TOKEN` | — | GitHub API token |
| `GITHUB_REPO` | — | `owner/repo` for issues |
| `GITHUB_ISSUE_LABELS` | `support,appliance` | Comma-separated labels |
| `GITHUB_ISSUE_MIN_CONFIDENCE` | `high` | Minimum confidence to file |
| `SUPPORT_WEBHOOK_URL` | — | POST notification hook on ticket updates |
| `SUPPORT_WEBHOOK_SECRET` | — | Optional `X-Support-Webhook-Secret` header |

List endpoint: `GET /v1/tickets?appliance_id={id}` (entitlement-gated).

## CLI adapter (Phase 3)

Use an external AI CLI that reads the rendered prompt from **stdin** and prints a **JSON** `DiagnosisResult` to stdout:

```bash
export AI_CLI_ADAPTER=cli
export AI_CLI_COMMAND="python3 scripts/ai_diagnose_stub.py"
uvicorn src.main:app --reload --port 8090
```

Wire a real tool by setting `AI_CLI_COMMAND` to your CLI entrypoint. Optional env vars passed to the child process:

- `AI_CODE_ROOT` — primary backend checkout path
- `AI_CODE_ROOTS` — `os.pathsep`-joined list of all code roots

## Tests

```bash
pytest
```
