# REFACTO — appliance-support

Production-code refactoring guide for the InferEdge support/diagnostics service. Scope: `src/`, `scripts/`, `schemas/`. Excludes `tests/`.

---

## Executive summary

| Category | High | Medium | Low |
|----------|------|--------|-----|
| Security / correctness | 2 | 0 | 0 |
| Code duplication | 2 | 4 | 5 |
| Hardcoded values | 1 | 6 | 3 |
| Poor design | 0 | 7 | 4 |

Highest-impact issues: **missing entitlement check on ticket GET**, **in-memory rate limiter**, **triplicated stub diagnosis heuristics**, and **redaction pattern mismatch** with appliance-console.

---

## Disk space

Measured share of the ownedge workspace (~1.2 GB total):

| Path | Size | Category |
|------|------|----------|
| `src/` | ~224 KB | Python source |
| `tests/` | ~124 KB | Test source (out of REFACTO scope) |
| `.venv/` | ~24 KB | Local virtualenv (minimal) |
| `.pytest_cache/` | ~20 KB | Test cache |

**appliance-support is essentially entirely source code** — no large build artifacts. Disk is not a concern for this repo.

---

## 1. Security and correctness

### 1.1 No entitlement check on ticket GET — HIGH

**Location:** `src/main.py` — `GET /v1/tickets/{ticket_id}` returns any ticket by UUID with no `appliance_id` or entitlement verification.

Ticket IDs are UUIDs (unguessable but leakable via logs, webhooks, GitHub issues).

**Action:** Require `appliance_id` query param and verify it matches the stored bundle; or use signed ticket tokens.

---

### 1.2 In-memory rate limiter — HIGH

**Location:** `src/main.py` — `_ticket_counts` dict is process-local, resets on restart, incorrect under multiple workers.

**Action:** Redis or SQLite sliding window keyed by `appliance_id`. Externalize window via `SUPPORT_RATE_LIMIT_WINDOW_SEC` (currently hardcoded `3600`).

---

## 2. Code duplication

### 2.1 Stub diagnosis heuristics (triplicated) — HIGH

Same OOM / DEGRADED+exit_code / READY heuristics in three places with drift:

| Location | Notes |
|----------|-------|
| `src/ai/stub.py` | Full heuristic engine; hardcoded `inferedge-phase1/controller/reconciler.py` path |
| `scripts/ai_diagnose_stub.py` | Simpler keyword rules, different summaries |
| `appliance-console/lib/support/mock.ts` | Parallel TypeScript mock for offline console |

InferEdge has a richer marker set in `controller/serving/load_errors.py` that none of these use.

**Action:** Extract a single shared rules spec (YAML/JSON) or canonical Python module. CLI stub and console mock consume generated fixtures. Delete duplicated branching logic.

---

### 2.2 Secret redaction (cross-repo, divergent) — HIGH

| File | Patterns |
|------|----------|
| `src/redact.py` | `SENSITIVE_KEYS` + 5 regexes (incl. JSON key patterns) |
| `appliance-console/lib/support/redact.ts` | Same keys, only 2 regexes — **no** `"hf_token"` / `"password"` / `"secret"` JSON patterns |

Console scrubs before send; support re-scrubs in `main.py`. Defense-in-depth is fine, but **pattern mismatch** means secrets can pass console scrub and fail support's `contains_secrets` check (400), or leak if patterns diverge further.

**Action:** Single `support-redaction.yaml` (keys + patterns) code-generated for Python and TypeScript; contract test across repos.

---

### 2.3 `SubprocessCLIAdapter` subprocess runners — MEDIUM

**Location:** `src/ai/cli.py` — `_run_with_stdin` and `_run_with_prompt_file` duplicate:
- `subprocess.run` + timeout/OSError handling
- return-code handling (stdin path treats 124/137 as transient; prompt-file path does not)
- empty stdout check
- stderr truncation `[-500:]`

**Action:** Extract `_execute_cli(cmd, env) -> CompletedProcess` with unified exit-code policy.

---

### 2.4 Redaction helpers overlap internally — LOW

`src/redact.py`:
- `scrub_object` duplicates string scrubbing from `_scrub_value`
- List handling differs between the two functions

**Action:** One recursive `scrub(value, key=None)`; drop `scrub_object` or make it a thin alias.

---

### 2.5 Entitlement denial messages — LOW

`src/billing/stub.py` repeats `"Support subscription required for this appliance."` three times. Same string in `appliance-console/lib/support/mock.ts` and fallback in `src/main.py`.

**Action:** `ENTITLEMENT_DENIED_MESSAGE` constant in `schemas.py` or `constants.py`.

---

### 2.6 Subscription 403 response shape — LOW

`src/main.py` `create_ticket` and `list_tickets` are copy-pasted JSON bodies.

**Action:** `def subscription_required_response(entitlement) -> JSONResponse`.

---

### 2.7 Diagnosis JSON parsing in ticket reads — LOW

`src/tickets.py` — `_row_to_status` and `list_tickets_for_appliance` both parse `diagnosis_json` → `DiagnosisResult`.

**Action:** `_parse_diagnosis(row) -> DiagnosisResult | None` and `_row_to_summary(row)`.

---

### 2.8 Diagnose job failure handling — LOW

`src/jobs/diagnose.py` — `CLIPermanentError` and bare `Exception` blocks are identical.

**Action:** Single `_fail_ticket(ticket_id, bundle, error_msg)` helper.

---

### 2.9 Env boolean parsing — LOW

Repeated `os.environ.get(...).lower() in ("1", "true", "yes")` in:
- `src/billing/stub.py`
- `src/ai/cli.py`
- `src/vendor/github.py`

**Action:** `def env_flag(name: str, default: bool = False) -> bool` in `config.py`.

---

### 2.10 Registry adapter pattern — LOW

`src/ai/registry.py` and `src/billing/registry.py` share env-switch pattern but differ in error type (`CLIPermanentError` vs `ValueError`).

**Action:** Shared `load_adapter(env_var, mapping)` helper; consistent error type.

---

### 2.11 Cross-repo log truncation constants — MEDIUM

| Location | Constants |
|----------|-----------|
| `inferedge-phase1/controller/support_diagnostics.py` | `LOG_TAIL_LINES = 200`, `LOG_MAX_BYTES = 64 * 1024` |
| `appliance-console/lib/support/redact.ts` | `maxLines = 200`, `maxBytes = 64 * 1024` |

**Action:** Document in shared schema; all three repos import the same limits.

---

### 2.12 Cross-repo API types / bundle schema — MEDIUM

`DiagnosticBundle`, `DiagnosisResult`, ticket DTOs defined in:
- `src/schemas.py`
- `schemas/*.json` (unused at runtime)
- `appliance-console/lib/support/types.ts` (stricter `health` typing)

**Action:** Generate Pydantic + TypeScript from `schemas/*.json`; validate inbound bundles against JSON Schema in `main.py`.

---

## 3. Hardcoded values

### 3.1 Ticket lifecycle statuses — HIGH

Free strings with no enum/validation:

| Value | Locations |
|-------|-----------|
| `"queued"` | `src/tickets.py`, `src/main.py` |
| `"diagnosing"` | `src/jobs/diagnose.py` |
| `"complete"` | `src/jobs/diagnose.py`, `src/main.py` |
| `"failed"` | `src/jobs/diagnose.py` |

**Action:** `TicketStatus` `StrEnum` in `schemas.py`; DB CHECK constraint or app-level validation on write.

---

### 3.2 Appliance health states in stub logic — MEDIUM

`src/ai/stub.py` compares `state == "READY"`, `"DEGRADED"`, default `"UNKNOWN"`. InferEdge defines `ApplianceState` with `BOOT`, `RECONCILING`, `FAILED`, etc. Stub ignores those states.

**Action:** Import or mirror `ApplianceState` enum; extend heuristics for `FAILED` / `RECONCILING`.

---

### 3.3 Verdict / confidence literals — MEDIUM

Used in Pydantic `Literal` (`src/schemas.py`), GitHub gating (`src/vendor/github.py`), stub, and script — but GitHub hardcodes:

```python
confidence_rank = {"low": 0, "medium": 1, "high": 2}
diagnosis.verdict == "likely_bug"
```

**Action:** `Verdict`, `Confidence` enums; `CONFIDENCE_RANK` module constant; `GITHUB_ISSUE_VERDICTS` config.

---

### 3.4 OOM / resource signal keywords — LOW

`src/ai/stub.py`: `("out of memory", "oom", "cuda", "insufficient")` — duplicated in `scripts/ai_diagnose_stub.py` and `appliance-console/lib/support/mock.ts`. InferEdge `load_errors.py` has a richer set.

**Action:** `RESOURCE_ERROR_SIGNALS` frozenset in shared config; align all repos.

---

### 3.5 Hardcoded product path in stub — MEDIUM

`src/ai/stub.py`: `"inferedge-phase1/controller/reconciler.py"` — product-specific path in generic support service.

**Action:** Config map `CODE_HINTS` keyed by error pattern or env `SUPPORT_CODE_HINTS_JSON`.

---

### 3.6 Rate limit window — MEDIUM

`src/main.py`: `3600` seconds hardcoded; limit count is env-driven but window is not.

**Action:** `SUPPORT_RATE_LIMIT_WINDOW_SEC` env var.

---

### 3.7 CLI transient exit codes — LOW

`src/ai/cli.py`: `completed.returncode in (124, 137)` — only in stdin path, not prompt-file path.

**Action:** `TRANSIENT_CLI_EXIT_CODES = frozenset({124, 137})` applied in both runners.

---

### 3.8 HTTP / API magic values — LOW

| Value | Location |
|-------|----------|
| GitHub API version `2022-11-28` | `src/vendor/github.py` |
| `httpx` timeout `30.0` / `15.0` | `github.py`, `notify.py` |
| Default labels `"support,appliance"` | `github.py` |
| Error code `"subscription_required"` | `src/main.py` |
| User-facing errors in diagnose job | `src/jobs/diagnose.py` |

**Action:** Central `config.py` with env overrides.

---

### 3.9 Code context repo map — MEDIUM

`src/code_context/manager.py`: `DEFAULT_REPOS` hardcodes repo names and directory layout (`parents[3] / default_dir`). Version sentinel strings `"unknown"`, `"dev"`, `"mock"`.

**Action:** `CODE_CONTEXT_REPOS` YAML (extend `versions.yaml`) for repo keys, paths, fallback refs.

---

### 3.10 Support client version — LOW

`"1.0.0"` in `src/schemas.py` and `appliance-console/lib/support/bundle.ts` — can drift.

**Action:** Single version in JSON schema default or build-time injection.

---

## 4. Poor design choices

### 4.1 `BackgroundTasks` for diagnosis — MEDIUM

**Location:** `src/main.py` — long-running AI work (up to 180 s + retries) on FastAPI background tasks; no persistence, retry queue, or worker isolation.

**Action:** Dedicated job queue (ARQ, Celery, or SQLite outbox + worker process).

---

### 4.2 New SQLite connection per DB operation — MEDIUM

**Location:** `src/tickets.py` opens `aiosqlite.connect(DB_PATH)` in 7 separate functions with no connection pool.

**Action:** `async with get_db() as db` dependency or single connection in lifespan for low-traffic MVP.

---

### 4.3 Git checkout side effects on every diagnosis — MEDIUM

**Location:** `src/code_context/manager.py` — `git fetch` + `checkout --detach` on shared repo dirs during each ticket; races under concurrency; mutates working trees.

**Action:** Per-ticket worktrees, read-only mounted refs, or pre-materialized version cache.

---

### 4.4 Layered timeouts (confusing semantics) — MEDIUM

- `DIAGNOSIS_TIMEOUT_SEC` default 180 (`src/jobs/diagnose.py`) wraps entire adapter call
- `AI_CLI_TIMEOUT_SEC` default 120 (`src/ai/cli.py`) wraps subprocess

Job timeout can fire while CLI is still running.

**Action:** Single timeout at job level **or** CLI level; document precedence; align defaults.

---

### 4.5 JSON schemas unused at runtime — MEDIUM

`schemas/diagnostic-bundle.v1.json` and `diagnosis-result.v1.json` exist but nothing in `src/` validates against them. Pydantic models can drift (e.g. `health: dict[str, Any]` vs console's typed health).

**Action:** Validate `POST /v1/tickets` with `jsonschema` before Pydantic, or generate Pydantic from schema.

---

### 4.6 Loose `health` typing — MEDIUM

`src/schemas.py`: `health: dict[str, Any]` — stub and AI rely on `state`, `last_error`, `actual` without schema enforcement.

**Action:** `HealthSummary` model aligned with `appliance-console/lib/support/types.ts` and controller status shape.

---

### 4.7 Inline DB migration — LOW

`src/tickets.py` — `_migrate_columns` only adds `github_issue_url`; no versioned migration framework.

**Action:** Alembic or numbered SQL migrations for production evolution.

---

### 4.8 Double scrub + validate flow — LOW

`src/main.py`: scrub → JSON dump → `contains_secrets` → re-validate. Redundant if scrub is correct; `contains_secrets` only checks regexes, not redacted keys.

**Action:** Trust scrub output or run `contains_secrets` on pre-scrub input only.

---

### 4.9 `get_ticket` after workflow refetch — LOW

`src/vendor/workflow.py` and `src/jobs/diagnose.py` both fetch ticket from DB for notifications.

**Action:** Pass diagnosis/status into `send_ticket_notification` from caller.

---

### 4.10 Billing registry only supports stub — MEDIUM

`src/billing/registry.py` — only `"stub"` adapter; production billing path not pluggable despite `DESIGN.md` promises.

**Action:** Define `BillingEntitlementAdapter` HTTP implementation; fail fast at startup if `BILLING_ADAPTER` unknown in prod.

---

### 4.11 DESIGN.md vs implementation gap — LOW

DESIGN.md non-goals say "Automatic bug filing in GitHub (defer to Phase 4)" but `src/vendor/github.py` implements it behind `GITHUB_ISSUE_ENABLED`.

**Action:** Update DESIGN.md or gate feature behind explicit phase flag.

---

## 5. Cross-repo pattern summary

| Pattern | appliance-support | inferedge-phase1 | appliance-console |
|---------|-------------------|------------------|-------------------|
| Diagnostic collection | Consumes bundle | `support_diagnostics.py` builds host/logs | `bundle.ts` assembles bundle |
| Redaction | `redact.py` | N/A (console redacts) | `redact.ts` |
| Stub diagnosis | `ai/stub.py` + script | N/A | `mock.ts` |
| OOM markers | stub keyword list | `load_errors.py` (canonical) | `mock.ts` keyword list |
| API types | `schemas.py` + unused JSON | N/A | `types.ts` |
| Entitlement | `billing/stub.py` | N/A | `client.ts` + `mock.ts` |
| Log tail limits | N/A | 200 lines / 64 KB | Same in `truncateLogTail` |
| Appliance states | String compares in stub | `ApplianceState` enum | Hardcoded strings |

**Action:** Make `schemas/` the contract hub. Generate Python enums, TypeScript types, and redaction rules from it. InferEdge `load_errors.py` markers should feed the stub rules spec.

---

## 6. Prioritized roadmap

| Priority | Item | Effort |
|----------|------|--------|
| **P0** | Entitlement + appliance ownership check on `GET /v1/tickets/{id}` | Small |
| **P0** | Unify redaction rules with appliance-console (shared spec + tests) | Medium |
| **P0** | Replace in-memory rate limiter; externalize rate-limit window | Medium |
| **P1** | `TicketStatus` / `Verdict` / `ApplianceState` enums | Small |
| **P1** | Consolidate stub heuristics; remove drift between stub/script/mock | Medium |
| **P1** | Align OOM markers with `inferedge-phase1/controller/serving/load_errors.py` | Small |
| **P2** | Refactor `cli.py` subprocess duplication; fix 124/137 in both paths | Small |
| **P2** | Job queue for `run_diagnosis`; SQLite connection pooling | Medium |
| **P2** | Wire JSON schemas into runtime validation; typed `HealthSummary` | Medium |
| **P3** | `config.py` for env flags, timeouts, messages | Small |
| **P3** | Git worktrees for code context | Medium |
| **P3** | Generate TS/Python types from `schemas/` | Medium |

### Suggested implementation order

1. Security fixes (ticket GET entitlement, durable rate limiter)
2. Shared redaction YAML + contract tests with console
3. Enums for ticket status, verdict, appliance state
4. Stub rules spec — delete `scripts/ai_diagnose_stub.py` duplication; sync console mock
5. JSON Schema validation on inbound bundles
6. Job queue and DB pooling before scaling ticket volume

---

## 7. Production files reviewed

**`src/`:** `main.py`, `tickets.py`, `schemas.py`, `entitlement.py`, `redact.py`, `jobs/diagnose.py`, `ai/*`, `billing/*`, `code_context/manager.py`, `vendor/*`

**`scripts/`:** `ai_diagnose_stub.py`

**`schemas/`:** `diagnostic-bundle.v1.json`, `diagnosis-result.v1.json`

**Supporting:** `code_context/versions.yaml`, `prompts/diagnose.txt`, `compose.yml`