# Appliance Support — Remaining Work

Tracks what is still open before AI-assisted support is production-ready and fully integrated.

**This file lives in the support service repo** (`appliance-support` / botland/support).

**Repos involved:**

| Repo | Role |
|------|------|
| This repo (`appliance-support`) | Hosted API, entitlement, tickets, AI CLI, code context |
| `appliance-console` | Support UI, bundle assembly, outbound push |
| `inferedge-phase1` (ownedge monorepo) | Controller diagnostics + version stamps |
| `nocloud` | Billing/subscription DB, `aiAssistedSupport` product |

**Last updated:** 2026-07-09

---

## Completed

### MVP (design phases 1–4)

- Console **Support** page: send report, preview, poll diagnosis, ticket history
- Support service: entitlement gate, tickets API, SQLite store, rate limit, redaction
- Controller `GET /support/diagnostics` and `version` on `GET /health`
- AI **stub** adapter + generic **subprocess CLI** adapter
- Diagnosis timeout/retry, optional GitHub issues + webhooks
- Per-repo unit tests

### Code context isolation (§3)

- Per-ticket git **worktrees** under `CODE_WORKTREE_ROOT/{ticket_id}/`
  - `appliance-console/` @ `software.console_version`
  - `appliance-backend/` @ `software.controller_version`
  - `_ai/` artifacts: `prompt.txt`, `bundle.json`, CLI stdout/stderr
- Strict refs: SHA or tag only; `dev`/`unknown`/`mock` → ticket failed + email `support@ownedge.ai`
- Env: `CODE_ROOT_APPLIANCE_CONSOLE`, `CODE_ROOT_APPLIANCE_BACKEND`, `CODE_WORKTREE_ROOT`
- Optional `SUPPORT_KEEP_TICKET_WORKTREES` to retain trees for investigation

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
- Docker: mount `~/.grok` → `/root/.grok` (`GROK_HOME`); `PATH` includes `/root/.grok/bin` (host: `grok login`)

### Billing adapter (code present)

- `BILLING_ADAPTER=postgres` + `DATABASE_URL` reads nocloud
  `appliances` ⨝ `service_subscriptions` for `service_key = 'aiAssistedSupport'`
- Default remains `stub` until prod wiring

---

## 1. Billing and entitlement (blocking for paid service)

| Item | Notes |
|------|--------|
| Production wiring | Point support at billing DB (`BILLING_ADAPTER=postgres`, `DATABASE_URL`); document in compose/ops. Default is still `stub`. |
| Subscription lifecycle | `aiAssistedSupport` is **internal-only** in nocloud (`INTERNAL_SERVICE_KEYS`) — not on landing/checkout (storefront sells `prioritySupport`). Stripe sync can write the row if metadata carries the key. Need customer-facing buy path and clear entitled/not entitled UX. |
| Schema / ownership | Schema exists in nocloud (`customers`, `appliances`, `service_subscriptions`). TBD: shared Postgres vs read replica for support service. |

---

## 2. Production deployment and appliance integration

| Item | Notes |
|------|--------|
| Host support service | Not deployed to a production URL (e.g. `support.ownedge.ai`). Local `docker compose` only. |
| Unified stack wiring | Appliance compose does not set `SUPPORT_SERVICE_URL` / `SUPPORT_ENABLED` on the console container. |
| Docs | Root / console docs should describe support enablement end-to-end. |
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
| Ticket poll binding | Optional: require `appliance_id` match on poll (today `ticket_id` is capability token) |
| Authenticated diagnostics | `GET /support/diagnostics` is public like `/status` |
| Webhook / GitHub / SMTP secrets | Document rotation and least privilege |

---

## 7. Explicitly deferred

- Multi-turn support chat in the console
- Email/push to appliance admins (ops webhook/email alerts exist for failures)
- Per-appliance API tokens on device

---

## 8. Testing and E2E

| Item | Notes |
|------|--------|
| Cross-repo E2E script | Support + console → submit → poll → verdict |
| Diagnostics secret scan | Automated “no secrets in diagnostics” |
| Load / concurrency | Parallel tickets + isolated worktrees |

---

## Suggested implementation order

1. **Ops smoke:** stamped appliance → worktrees → `AI_CLI_ADAPTER=cli` (Grok) → diagnosis  
2. **Billing prod path:** postgres adapter + sell/provision `aiAssistedSupport`  
3. **Deploy + compose wiring + TLS + retention purge**  
4. **Multi-node diagnostics (§5b)**  
5. **E2E script + diagnostics polish (§5) + security (§6)**  

---

## Open decisions

- Billing DB access for support (shared vs replica) and product packaging for `aiAssistedSupport`
- Ticket poll must verify `appliance_id`?
- Full bundle retention vs hashed summary after diagnosis
- Default IP masking policy
- Multi-node: head-only aggregation vs worker-initiated; max nodes; offline node behaviour
- Worktree pool size vs clone cost at scale
