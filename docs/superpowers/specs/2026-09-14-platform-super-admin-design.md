# Platform Super Admin — Design

Status: Approved for planning
Date: 2026-09-14

## Purpose

IDMS today has exactly one tier of account: an organization user (`OWNER`/`ADMIN`/`MEMBER`/`VIEWER`), scoped entirely to their own org via Postgres Row-Level Security (RLS). There is no way for DOK Solutions to see or manage the platform across customers. This feature adds a **platform super admin** capability that can:

- See every organization, with per-org user count, document count, AI token usage, and AI cost.
- Toggle four AI capabilities on/off per organization: Q&A/chat, summarization, AI answer-summary in search, and structured extraction.
- View a per-org document list (metadata only — no content/preview access).
- Suspend/reactivate an organization (blocks its users from using the product).

Out of scope for this iteration (explicitly deferred, confirmed during brainstorming):

- Per-user actions across orgs (deactivating an individual user, resetting a password) — stays with each org's own OWNER/ADMIN via the existing Team Panel.
- Editing an org's plan name or `monthly_page_quota`.
- Time-series/trend usage charts — summary totals only.
- Document content/preview access for the platform admin.

## Why a separate identity, not a role on `users`

Every existing tenant table (`users`, `documents`, `document_chunks`, `api_usage`, `extraction_templates`, `extractions`, `audit_logs`) has RLS **FORCE**d, gated on `current_setting('app.current_org_id')`, set per-transaction via `SET LOCAL` in `get_db`. This is deliberately defense-in-depth: even a missed `org_id` filter in application code cannot leak cross-tenant data, because the database itself refuses rows outside the current org — including for the table owner, since `FORCE ROW LEVEL SECURITY` applies to everyone except a role with the `BYPASSRLS` attribute.

A super admin needs to see rows across _all_ orgs. Two ways to get there were considered:

1. **Special-case a role value inside the existing model.** Add `SUPER_ADMIN` to the `users.role` enum, and skip the `SET LOCAL app.current_org_id` step in `get_db` when the current user has that role. Rejected: this means every RLS-protected query in the codebase implicitly runs unscoped for such a user, and a super admin account would still need to "belong" to some org, which is a modeling lie. A single missed `org_id` filter somewhere in application code — the exact class of bug RLS exists to catch — would now leak everything, silently.
2. **A fully separate identity, authenticated separately, reading through a dedicated DB role with `BYPASSRLS`.** The database enforces the isolation boundary the same way it does for everyone else — this new role either has the bypass attribute or it doesn't, and only the platform-admin service layer's connection uses it. Chosen.

This keeps the blast radius of a bug in the platform-admin code path contained to that code path, and keeps the RLS story for the rest of the app exactly as strong as it is today.

## Data model changes

### New table: `platform_admins`

| Column          | Type                                 | Notes                                   |
| --------------- | ------------------------------------ | --------------------------------------- |
| `id`            | UUID, PK                             | `uuid.uuid4()` default                  |
| `email`         | text, unique, not null               | Globally unique, like `users.email`     |
| `password_hash` | text, not null                       | Argon2 via `passlib`, same as org users |
| `is_active`     | boolean, not null, default `true`    | Kill switch without deleting the record |
| `created_at`    | timestamptz, not null, default now() |                                         |
| `last_login_at` | timestamptz, nullable                | Updated on successful login             |

Not RLS-protected — this table holds no tenant data, and only the regular `idms_app` connection (not the BYPASSRLS role) needs to read/write it, since login/auth for platform admins is a platform-level concern, not a per-tenant one.

### `organizations` — 5 new columns

| Column                     | Type    | Default | Meaning when true/false                                                                                                      |
| -------------------------- | ------- | ------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `is_suspended`             | boolean | `false` | `true` blocks all of that org's users from logging in or continuing an existing session                                      |
| `ai_qa_enabled`            | boolean | `true`  | Gates `/ai/documents/{id}/ask` and `/ai/chat`                                                                                |
| `ai_summarization_enabled` | boolean | `true`  | Gates `/ai/documents/{id}/summarize`                                                                                         |
| `ai_search_answer_enabled` | boolean | `true`  | Gates the AI-generated answer summary in `GET /search` (plain hybrid search results still return)                            |
| `ai_extraction_enabled`    | boolean | `false` | Gates `/templates/extract`. Defaults off — this is the newest, least proven AI capability and should be opt-in per customer. |

### New Postgres role: `idms_platform_admin`

Created via `CREATE ROLE idms_platform_admin WITH LOGIN PASSWORD '<from env>' BYPASSRLS;` in the migration. `idms_app` is the Postgres superuser in this project's Docker Compose setup (it's the `POSTGRES_USER` on the `pgvector/pgvector:pg16` image), so it can grant `BYPASSRLS` directly — no extra deployment step needed for local/staging. **Production note:** on a managed Postgres (e.g. Cloud SQL), the connecting migration role may not have `BYPASSRLS`-granting privilege; if so this one statement needs to run once as a DBA/superuser step outside the normal migration run. The spec calls this out explicitly so it isn't discovered as a surprise at deploy time.

New env var: `PLATFORM_ADMIN_DATABASE_URL` (same host/db, different user/password) — a second async SQLAlchemy engine in `app/core/db.py`, used exclusively by the platform-admin service layer.

## Auth

### Login

`POST /api/v1/auth/login` keeps its existing URL and request shape (`email`, `password`). Internally:

1. Look up `email` in `platform_admins`. If found and `is_active` and the password matches: issue an access token with `type: "platform_admin"` (no `org_id`, no `role` claim) and a refresh token stored in Redis under `admin_refresh:<uuid>` (namespaced separately from `refresh:<uuid>` so the two token spaces can never collide or be confused). Update `last_login_at`. Response body includes `account_type: "platform_admin"` so the frontend knows where to redirect.
2. Otherwise, fall through to the existing org-user login path unchanged, with one addition: if the matched user's organization has `is_suspended = true`, return 403 with a clear message instead of issuing tokens. Response body for a normal login includes `account_type: "org_user"`.

Email spaces are already independent (`platform_admins.email` and `users.email` are different tables), so a collision just means the platform-admin lookup takes priority — acceptable since these are managed accounts, not self-registered.

### Suspension takes effect immediately, not just on next login

`get_current_user` (the existing per-request JWT dependency in `core/deps.py`) is extended to check `organizations.is_suspended` for the caller's `org_id` and return 403 if true. This is one extra indexed lookup per authenticated request (org is already being fetched/joined in most flows, or is a cheap PK lookup) — acceptable given it's the only way an already-issued 15-minute access token actually stops working before it naturally expires.

### Platform admin auth dependency

`get_current_platform_admin` in `core/deps.py`: decodes the JWT, requires `type == "platform_admin"`, loads the `platform_admins` row, 401s if not found/inactive. This (not `get_current_user`) protects every route under the new router.

## API surface

New router `api/app/api/v1/platform_admin.py`, mounted at `/api/v1/platform-admin`, every route behind `get_current_platform_admin`. All queries here go through `get_admin_db` (a new dependency yielding a session on the `idms_platform_admin` engine — no `SET LOCAL app.current_org_id`, because the whole point is reading across orgs).

- `GET /platform-admin/organizations` — one row per org: `id`, `name`, `slug`, `plan`, `is_suspended`, `monthly_page_quota`, `pages_used_this_month`, `user_count`, `document_count`, `ai_tokens_total`, `ai_cost_total_usd`, and the 4 AI toggle booleans. Aggregates computed with `COUNT`/`SUM` over `users`, `documents`, `api_usage` grouped by `org_id` — this is the same shape of aggregation `monitoring.py` already does for the daily cost report, just per-org instead of platform-wide.
- `PATCH /platform-admin/organizations/{org_id}` — body may include any subset of `is_suspended`, `ai_qa_enabled`, `ai_summarization_enabled`, `ai_search_answer_enabled`, `ai_extraction_enabled`. Updates only the fields provided.
- `GET /platform-admin/organizations/{org_id}/documents` — that org's documents: `id`, `filename`, `mime_type`, `size_bytes`, `status`, `page_count`, `uploaded_by` (email, via join), `created_at`. No `extracted_text`, no presigned preview URL — metadata only, per the confirmed scope.

## AI toggle enforcement

Each gated code path loads the relevant flag from the org record it already has in scope and short-circuits before calling `_call_llm`/the provider, returning a plain, unambiguous string (not an exception) — consistent with how `_call_llm` already returns `"[AI disabled: no GROQ_API_KEY or GOOGLE_AI_API_KEY configured]"` when no provider is configured:

- `services/ai.py`: `ask_document`, `ask_org` check `ai_qa_enabled`; `summarize_document` checks `ai_summarization_enabled`.
- `services/search.py`: `hybrid_search` checks `ai_search_answer_enabled` before generating the answer summary — the underlying semantic+full-text results are returned either way.
- `services/extraction.py`: `extract_fields` checks `ai_extraction_enabled` and raises a `ValueError` (consistent with its existing "Document not found"/"Template not found" error style, which the router already maps to an HTTP error) if off.

## Frontend

- `web/lib/auth.ts`: `login()` reads `account_type` from the response and stores it alongside the tokens (sessionStorage, same as today).
- Post-login redirect: `account_type === "platform_admin"` → `/admin`; otherwise → `/dashboard` (unchanged).
- New `web/app/admin/layout.tsx` + `web/app/admin/page.tsx`: an organizations table (name, plan, users, docs, AI tokens, AI cost, quota usage, suspend switch, 4 AI-feature switches) styled consistently with the existing dashboard (same CSS custom properties, no new UI library). Clicking a row opens that org's document list (reusing the existing table-row visual pattern from `DocumentList.tsx` where reasonable, metadata columns only).
- No changes to the existing `/dashboard` for org users beyond what suspension already causes (a 403 on their next request logs them out via the existing "redirect to /login on auth failure" behavior already present in the dashboard).

## Bootstrap

`api/scripts/create_platform_admin.py` — a standalone script (`uv run python -m app.scripts.create_platform_admin --email you@example.com`), prompts for a password (not passed as an argv to avoid shell history), hashes it, inserts into `platform_admins`. Never exposed as an API endpoint. Documented in a short section added to the project README or an ops note — not part of this spec's UI.

## Error handling

- Suspended org, org-user request: 403 `{"detail": "This organization has been suspended. Contact support."}`.
- Non-admin token used against `/platform-admin/*`: 401 (falls out of `get_current_platform_admin` the same way `get_current_user` already 401s on a bad/missing token).
- AI toggle off: the calling endpoint returns 200 with the disabled-message string in the same field a real AI answer would occupy (matches existing `_call_llm` disabled-message convention) — not an error status, since "AI is off for your plan" is an expected, not exceptional, state for Q&A/summarize/search; extraction is the one exception where a `ValueError` maps to a 4xx, matching its existing style for "can't do this right now" conditions.
- `PATCH /platform-admin/organizations/{org_id}` on an unknown `org_id`: 404.

## Testing

- **Auth routing**: login with a `platform_admins` email issues a `type: platform_admin` token and `account_type: "platform_admin"`; login with an org-user email is unaffected; a suspended org's user gets 403 on login.
- **Suspension takes effect mid-session**: issue a token, suspend the org, confirm the next authenticated request 403s without waiting for token expiry.
- **RLS bypass boundary**: a query through `get_admin_db` sees rows from multiple orgs in one call (proves the bypass works); a query through the normal `get_db` for one org never sees another org's rows even when both exist in the DB (proves the bypass is contained to the admin path only).
- **AI toggles**: for each of the 4 flags, off → the gated call returns the disabled message/error without hitting the LLM provider (mock/assert not called); on → behaves as today.
- **Platform-admin endpoints reject org-user tokens** and vice versa.
- Manual verification of the `/admin` UI against the running Docker stack: log in as the bootstrapped platform admin, see both existing orgs (`abc`, `dok`) with correct user/doc counts, flip a toggle and confirm it's reflected, suspend an org and confirm that org's user is locked out.
