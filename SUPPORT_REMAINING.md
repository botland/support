# Appliance Support — Remaining Work

Tracks what is still open before AI-assisted support is production-ready and fully integrated.

**This file lives in the support service repo** (`appliance-support` / botland/support).

**Repos involved:**

| Repo | Role |
|------|------|
| This repo (`appliance-support`) | Hosted API, entitlement, tickets, AI CLI, code context, product guide |
| `appliance-console` | Support UI, bundle assembly, outbound push |
| `inferedge-phase1` (ownedge monorepo) | Controller diagnostics + version stamps + compose wiring |
| `nocloud` | Billing/subscription DB, storefront guide BFF, `aiAssistedSupport` product |

**Last updated:** 2026-07-12

---

## Completed

### MVP (design phases 1–4)

- Console **Support** page: send report, preview, poll diagnosis, ticket history
- Support service: entitlement gate, tickets API, SQLite store, rate limit, redaction
- Controller `GET /support/diagnostics` and `version` on `GET /health`
- AI **stub** adapter + generic **subprocess CLI** adapter
- Diagnosis timeout/retry, optional GitHub issues + webhooks
- Per-repo unit tests; cross-repo support polling limits contract

### Code context isolation (§3)

- Per-ticket git **worktrees** under `CODE_WORKTREE_ROOT/{ticket_id}/`
  - `appliance-console/` @ `software.console_version`
  - `appliance-backend/` @ `software.controller_version`
  - `_ai/` artifacts: `prompt.txt`, `bundle.json`, CLI stdout/stderr
- Strict refs: SHA or tag only; `dev`/`unknown`/`mock` → ticket failed + email `support@ownedge.ai`
- Env: `CODE_ROOT_APPLIANCE_CONSOLE`, `CODE_ROOT_APPLIANCE_BACKEND`, `CODE_WORKTREE_ROOT`
- Optional `SUPPORT_KEEP_TICKET_WORKTREES` to retain trees for investigation
- Docker: `safe.directory` + persistent worktree path mounts

### Version stamping (console + backend)

- Stack flag `APPLIANCE_PROD` + `scripts/resolve-versions.sh` (inferedge compose path)
  - `false`: stamp HEAD SHA on any branch
  - `true`: require branch **`prod`** on backend monorepo + console; stamp HEAD SHA
- Docker bake: `CONTROLLER_VERSION` / `APPLIANCE_CONSOLE_VERSION` (or `APP_VERSION` build-arg)
- Console bundle uses stamped env only (not npm package version)

### AI CLI harness (§4)

- Tool-agnostic: `AI_CLI_ADAPTER=cli` + `AI_CLI_COMMAND`
- **Default tool: Grok** — `scripts/ai_diagnose_grok.sh`
- Placeholders: `{prompt_file}`, `{bundle_file}`, `{code_root}`, `{code_roots}`, `{ticket_id}`
- Primary CWD = backend worktree (`AI_CLI_PRIMARY_ROOT=backend`); prompt requires investigating **both** console and backend
- Docker: mount `~/.grok` → `/root/.grok` (`GROK_HOME`); robust diagnosis JSON extraction
- Console poll window aligned with diagnosis timeout/retry contract (~6m)

### Appliance stack wiring

- `inferedge-phase1/compose.yml` passes `SUPPORT_SERVICE_URL` and `SUPPORT_ENABLED` (default true) into the console container
- `.env.example` documents enablement (`SUPPORT_SERVICE_URL=https://support.ownedge.ai`)

### Billing adapter (code present)

- `BILLING_ADAPTER=postgres` + `DATABASE_URL` reads nocloud
  `appliances` ⨝ `service_subscriptions` for `service_key = 'aiAssistedSupport'`
- nocloud entitlement DB schema + Stripe sync can provision the row
- Default remains `stub` until prod wiring

### Product guide chat (landing L1) — implemented

Public multi-turn guide via:

- Support service: `POST /v1/guide/sessions`, `.../messages`, `.../messages/stream` (SSE), `GET .../sessions/{id}`
- Sealed knowledge pack under `knowledge/product-guide/` (no code worktrees)
- Grok CLI wrapper `scripts/ai_guide_grok.sh`; compose default `GUIDE_AI_ADAPTER=cli`
- Storefront (nocloud): `/{locale}/support` + BFF `/api/guide/chat` and `/api/guide/chat/stream`
- Unit tests for guide API, stub heuristics, stream parse helpers

**Remaining for guide is ops only** (see §7b).

---

## 1. Billing and entitlement (blocking for production entitlement gate)

**Product packaging (decided):**

| Service key | Level | Scope | Commercial |
|-------------|-------|--------|------------|
| `aiAssistedSupport` | **L2** — AI-assisted diagnostics (this service) | Per-customer | Paid product; **$0 for now** (charge later) |
| `prioritySupport` (name may change) | **L3** — human/priority support | Per-customer | Paid product; **$0 for now** (charge later) |

L1 public product guide (landing chat) remains free and unentitled.

| Item | Notes |
|------|--------|
| Production wiring | Point support at billing DB (`BILLING_ADAPTER=postgres`, `DATABASE_URL`); document in compose/ops. Default is still `stub`. Gate tickets on `aiAssistedSupport` only (not L3). |
| Subscription lifecycle | Both L2 and L3 are per-customer services. Today `aiAssistedSupport` is still **internal-only** in nocloud (`INTERNAL_SERVICE_KEYS`); storefront surfaces L3-style priority support. Need: provision L2 (and L3) as free-of-charge paid SKUs, customer-facing enablement path, and clear entitled/not entitled UX on the appliance Support page. Stripe/metadata can already write rows when the service key is present. |
| Schema / ownership | Schema exists in nocloud (`customers`, `appliances`, `service_subscriptions`). TBD: shared Postgres vs read replica for support service. |

---

## 2. Production deployment

| Item | Notes |
|------|--------|
| Host support service | Not deployed to a production URL (e.g. `support.ownedge.ai`). Local `docker compose` + storefront → `127.0.0.1:8090` only. |
| Docs | End-to-end enablement (appliance + support host + billing) for ops runbooks. |
| Production datastore | Tickets still SQLite; production may need Postgres + backup policy. |
| TLS | Console → support must use HTTPS in production. |
| Retention purge | List API filters to 30 days; **old tickets/bundles are not deleted**. Need cleanup job/TTL. |
| Support host git | Keep `CODE_ROOT_*` clones able to fetch arbitrary SHAs (`git fetch --all` / by SHA) for dev-branch appliances. |

---

## 3. Code context — residual only

| Item | Notes |
|------|--------|
| Bare-mirror cache / concurrency caps | Optional at higher volume |
| `versions.yaml` aliases | Optional release labels only (not `dev` → `main`) |
| Live validation | Confirm worktrees + Grok against real stamped appliances |

---

## 4. AI CLI — residual only

| Item | Notes |
|------|--------|
| Live E2E with Grok | Host `grok login` + one real ticket smoke test (not automated in CI yet) |
| Named presets | Optional (`AI_CLI_ADAPTER=claude` etc.) — not required; switch via `AI_CLI_COMMAND` |
| Concurrency | Semaphore / single-flight under load |

---

## 5. Diagnostics and bundle gaps

| Item | Notes |
|------|--------|
| `controller_logs_tail` | Schema field still empty in controller collector; container logs only |
| IP masking | Secrets redacted; no configurable IP policy (RFC1918 keep vs redact all) |
| Bundle storage policy | Full JSON in SQLite forever; decide summary/hash after diagnosis |

---

## 5b. Multi-node diagnostics (head + workers)

**Status: not started.** Reports are **single-node only**.

For distributed clusters, head console should fan out diagnostics and attach per-node payloads (`bundle_version: 2`).

### Still to do

- [ ] Bundle schema v2 (`attachments.by_node` or equivalent)
- [ ] Head-console node selector + fan-out
- [ ] BFF routes + preview UI
- [ ] Worker-console messaging toward coordinator
- [ ] Tests (unreachable node, nested redaction)
- [ ] Document standalone vs distributed in `DESIGN.md`

---

## 6. Security hardening

| Item | Notes |
|------|--------|
| Ticket poll binding | **P0:** require `appliance_id` match (or entitlement) on `GET /v1/tickets/{id}` — today `ticket_id` is a capability token |
| Durable rate limits | In-memory counters for tickets + guide; replace before multi-instance deploy |
| Authenticated diagnostics | `GET /support/diagnostics` is public like `/status` (optional, policy-driven) |
| Webhook / GitHub / SMTP secrets | Document rotation and least privilege |

---

## 7. Explicitly deferred

- Multi-turn **diagnostic** support chat in the console (distinct from public product guide)
- Email/push to appliance admins (ops webhook/email alerts exist for failures)
- Per-appliance API tokens on device

## 7b. Product guide chat — ops remaining

Code is in place. Remaining:

- [ ] Prod Grok smoke (`GUIDE_AI_ADAPTER=cli`, real knowledge answers)
- [ ] Set `GUIDE_SERVICE_TOKEN` on support + storefront; enable `GUIDE_REQUIRE_TOKEN` if locking down
- [ ] Tune rate limits via env for production traffic
- [ ] Ship storefront guide UI/BFF (nocloud) with support service version

---

## 8. Testing and E2E

| Item | Notes |
|------|--------|
| Cross-repo E2E script | Support + console → submit → poll → verdict |
| Diagnostics secret scan | Automated “no secrets in diagnostics” |
| Load / concurrency | Parallel tickets + isolated worktrees |

---

## Suggested implementation order

1. **Ship guide** — commit storefront side + prod Grok smoke + optional token  
2. **Ops smoke (diagnose):** stamped appliance → worktrees → `AI_CLI_ADAPTER=cli` (Grok) → diagnosis  
3. **Security P0:** ticket poll binding + durable rate limiter  
4. **Billing prod path:** postgres adapter + provision L2 `aiAssistedSupport` (and L3) as $0 paid per-customer SKUs  
5. **Deploy + TLS + retention purge**  
6. **Multi-node diagnostics (§5b)** + `controller_logs_tail`  
7. **E2E script + diagnostics polish (§5)**  

---

## Open decisions

- Billing DB access for support (shared vs replica)
- How customers enable L2/L3 while free (auto-grant on hardware delivery vs opt-in catalog vs admin flag) — charge later without re-keying
- Final public name for L3 (`prioritySupport` provisional)
- Ticket poll must verify `appliance_id`? (**recommend yes**)
- Full bundle retention vs hashed summary after diagnosis
- Default IP masking policy
- Multi-node: head-only aggregation vs worker-initiated; max nodes; offline node behaviour
- Worktree pool size vs clone cost at scale
- Ticket store: stay on SQLite vs move to Postgres with support service HA
