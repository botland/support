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
| `AI_CLI_ADAPTER` | `stub` | `stub` (rules) or `cli` (subprocess — any tool via `AI_CLI_COMMAND`) |
| `AI_CLI_COMMAND` | Grok wrapper path in image | Production command; switch tools by changing this only |
| `AI_CLI_TIMEOUT_SEC` | `120` | Per-invocation subprocess timeout |
| `AI_CLI_USE_PROMPT_FILE` | `false` | Prefer file path / `{prompt_file}` (recommended for Grok) |
| `AI_CLI_CWD` | `code_root` | `code_root` (primary worktree) or `none` |
| `AI_CLI_PRIMARY_ROOT` | `backend` | `backend` \| `console` \| `first` — agent home + `AI_CODE_ROOT` |
| `SUPPORT_KEEP_TICKET_WORKTREES` | `false` | Keep `{ticket_id}/` worktrees + `_ai/` for human investigation |
| `GROK_HOME` | `$HOME/.grok` | Host path mounted at `/root/.grok` for auth + binary |
| `AI_PROMPT_TEMPLATE_PATH` | `prompts/diagnose.txt` | Diagnosis prompt template |
| `DIAGNOSIS_TIMEOUT_SEC` | `180` | Overall adapter call timeout (includes retries budget per attempt) |
| `DIAGNOSIS_MAX_RETRIES` | `2` | Retries on transient CLI/timeout failures |
| `DIAGNOSIS_RETRY_BACKOFF_SEC` | `2` | Backoff multiplier between retries |
| `BILLING_ADAPTER` | `stub` | Entitlement source (`stub` until billing DB is wired) |
| `CODE_ROOT_APPLIANCE_CONSOLE` | — | Source git clone for console (required for diagnosis code context) |
| `CODE_ROOT_APPLIANCE_BACKEND` | — | Source git clone for backend/controller (required for diagnosis code context) |
| `CODE_WORKTREE_ROOT` | next to DB path | Per-ticket isolated worktrees (`{ticket_id}/appliance-{console,backend}`) |
| `SUPPORT_ALERT_EMAIL` | `support@ownedge.ai` | Ops alerts (invalid appliance version / code context failures) |
| `SMTP_HOST` | — | If set, alerts are emailed; otherwise logged only |
| `SMTP_PORT` | `587` | SMTP port |
| `SMTP_USER` / `SMTP_PASSWORD` | — | Optional SMTP auth |
| `SMTP_FROM` | `noreply@ownedge.ai` | From address for alerts |

### Code context isolation

On each ticket, the service creates **git worktrees** under `CODE_WORKTREE_ROOT/{ticket_id}/` at the exact **git SHA or tag** reported in the bundle (`software.console_version`, `software.controller_version`). Placeholders like `dev` / `unknown` are rejected: the ticket fails and an alert is sent to `SUPPORT_ALERT_EMAIL`.

Example local `.env`:

```bash
CODE_ROOT_APPLIANCE_CONSOLE=/home/devel/ownedge/appliance-console
CODE_ROOT_APPLIANCE_BACKEND=/home/devel/ownedge/inferedge-phase1
CODE_WORKTREE_ROOT=/tmp/support-worktrees
SUPPORT_ALERT_EMAIL=support@ownedge.ai
```

Appliance builds stamp git SHAs via `APPLIANCE_PROD` + `./scripts/compose.sh` (see inferedge `resolve-versions.sh`):

- **`APPLIANCE_PROD=false` (dev):** any branch; HEAD SHA stamped. Support checks out that SHA if the commit is on the remote (push feature branches).
- **`APPLIANCE_PROD=true` (prod):** backend + console must be on branch **`prod`**; HEAD SHA stamped.

The support service has **no matching prod/dev mode** — it only needs reachable commits in `CODE_ROOT_*` clones. Prefer `git fetch --all --tags` (or fetch by SHA) on those clones so dev SHAs from any branch resolve.

**Docker:** mount `CODE_ROOT_*` host paths into the container (see `compose.yml`). Git 2.35+ rejects repos owned by a different UID unless marked `safe.directory` — the image entrypoint and `code_context.manager` handle this automatically when `CODE_ROOT_*` is set.

## API

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Liveness |
| `GET /v1/entitlement/{appliance_id}` | Subscription preflight |
| `POST /v1/tickets` | Submit diagnostic bundle |
| `GET /v1/tickets/{id}` | Poll ticket status / diagnosis |
| `POST /v1/guide/sessions` | Create product-guide chat session (public L1) |
| `POST /v1/guide/sessions/{id}/messages` | Non-streaming guide reply |
| `POST /v1/guide/sessions/{id}/messages/stream` | SSE streaming guide reply (`token` / `done` / `error`) |
| `GET /v1/guide/sessions/{id}` | Session + message history |

### Product guide chat (public L1)

Functional Q&A for the OwnEdge landing page (`/{locale}/support`). Uses a **sealed knowledge pack** under `knowledge/product-guide/` — **no code worktrees**, no diagnostic bundles, no stack-name leakage (Hugging Face is allowed). Limits are env-driven:

| Variable | Default | Purpose |
|----------|---------|---------|
| `GUIDE_AI_ADAPTER` | `cli` | **`cli`** = real generative AI (Grok subprocess); **`stub`** = keyword rules for unit tests only |
| `GUIDE_AI_CLI_COMMAND` | `scripts/ai_guide_grok.sh` | Guide CLI wrapper |
| `GUIDE_AI_CLI_TIMEOUT_SEC` | `120` | CLI timeout |
| `GUIDE_KNOWLEDGE_ROOT` | `knowledge/product-guide` | Product markdown pack |
| `GUIDE_PROMPT_PATH` | `prompts/product-guide.txt` | Guide system prompt |
| `GUIDE_MAX_MESSAGE_CHARS` | `2000` | Max user message length |
| `GUIDE_MAX_HISTORY_TURNS` | `12` | History window for the model |
| `GUIDE_SESSION_TTL_HOURS` | `24` | Session lifetime |
| `GUIDE_MAX_MESSAGES_PER_SESSION` | `40` | Cap messages per session |
| `GUIDE_RATE_LIMIT_PER_HOUR` | `20` | Per client IP (hour window) |
| `GUIDE_STREAM_CHUNK_CHARS` | `48` | SSE chunk size after CLI completion |
| `GUIDE_SERVICE_TOKEN` | — | Optional shared secret (`X-Guide-Token` / Bearer) |
| `GUIDE_REQUIRE_TOKEN` | `false` | Require token even if empty (misconfig-safe) |
| `GUIDE_ARTIFACT_ROOT` | `/data/guide` | Per-session CLI artifacts |

Storefront BFF: `POST /api/guide/chat` and `POST /api/guide/chat/stream` with `SUPPORT_SERVICE_URL` (+ optional `GUIDE_SERVICE_TOKEN`).

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

## AI CLI (production: Grok, easy to switch)

Architecture stays **tool-agnostic**: `AI_CLI_ADAPTER=cli` runs whatever `AI_CLI_COMMAND` is.  
**Default production tool is Grok** via [`scripts/ai_diagnose_grok.sh`](scripts/ai_diagnose_grok.sh).

### Per-ticket layout

```
CODE_WORKTREE_ROOT/{ticket_id}/
  appliance-console/     # worktree @ software.console_version
  appliance-backend/     # worktree @ software.controller_version  (primary CWD)
  _ai/
    prompt.txt           # full rendered prompt
    bundle.json          # diagnostic bundle
    code_roots.txt
    cli_stdout.txt       # raw tool output (investigation)
    cli_stderr.txt
```

The model is instructed to investigate **both** console and backend worktrees.

### Local with Grok

1. On the host: `grok login` (credentials in `~/.grok/auth.json`).
2. Run support with CLI adapter:

```bash
export AI_CLI_ADAPTER=cli
export AI_CLI_COMMAND="$(pwd)/scripts/ai_diagnose_grok.sh"
export AI_CLI_USE_PROMPT_FILE=true
export PATH="$HOME/.grok/bin:$PATH"
# CODE_ROOT_* + stamped appliance SHAs required for real tickets
uvicorn src.main:app --reload --port 8090
```

### Docker Compose + `~/.grok` volume

```bash
# Host: grok login once
export AI_CLI_ADAPTER=cli
export GROK_HOME=$HOME/.grok   # default
docker compose up --build
```

Compose mounts `${GROK_HOME:-$HOME/.grok}` → `/root/.grok` (auth + `bin/grok` on `PATH`).  
`HOME=/root` so Grok finds `auth.json`.

### Switch tools later

Keep `AI_CLI_ADAPTER=cli` and only change the command, e.g.:

```bash
AI_CLI_COMMAND="/opt/support/bin/ai_diagnose_other.sh --prompt {prompt_file} --cwd {code_root}"
```

Placeholders: `{prompt_file}`, `{bundle_file}`, `{code_root}`, `{code_roots}`, `{ticket_id}`.

Child env always includes: `AI_CODE_ROOT`, `AI_CODE_ROOTS`, `AI_PROMPT_FILE`, `AI_BUNDLE_FILE`,
`AI_ARTIFACT_DIR`, `AI_TICKET_ID`.

Stdout contract: a single **DiagnosisResult** JSON object (`schemas/diagnosis-result.v1.json`).

Dev without Grok:

```bash
export AI_CLI_ADAPTER=cli
export AI_CLI_COMMAND="python3 scripts/ai_diagnose_stub.py"
```

## Tests

```bash
pytest
```

