# URL Shortener API

![CI](https://github.com/meetshah27/DigitalOcean/actions/workflows/ci.yml/badge.svg)

A production-ready REST API that shortens long URLs, redirects short codes to
their original URL, and returns metadata about created links.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the request lifecycle and data-flow diagrams.

## Requirements

**Functional**
- Accept a long URL and generate a unique short code.
- Accept an optional user-defined custom alias, validated for format and uniqueness.
- Redirect a short code to its original URL.
- Return metadata for a created/existing short link.

**Non-functional**
- Input validation and sensible error handling on every endpoint; no internal error details (stack traces, exception text) ever returned to clients.
- No user content, PII, or secrets written to logs.
- All tunable values come from environment config, validated at startup, with safe defaults.
- Deterministic behavior under concurrent requests (alias collisions handled atomically at the DB layer).

**Out of scope**
- User accounts / authentication.
- Custom domains.
- Link-preview scraping or external URL-safety scanning.
- Rate limiting / abuse prevention.
- Admin UI.
- Multi-region / horizontal scaling infrastructure (see trade-offs below for how it *would* scale).

## API

| Method | Path | Success | Errors |
|---|---|---|---|
| `POST` | `/links` | `201 Created` (new), `200 OK` (idempotent replay) | `422` invalid url/alias/expiry, `409` alias already taken or `Idempotency-Key` reused with a different payload |
| `GET` | `/{code}` | `302 Found` (redirect) | `404` not found or expired |
| `GET` | `/links/{code}` | `200 OK` | `404` not found or expired |
| `GET` | `/links` | `200 OK` (paginated list) | — |

### Input schema (`POST /links`)

| Field | Type | Validation rule |
|---|---|---|
| `url` | string | required; must parse as `http`/`https`; max length 2048; extra/unknown fields rejected |
| `custom_alias` | string | optional; 3–30 chars; `[A-Za-z0-9_-]` only; case-sensitive; rejected if it matches a reserved word (`api`, `docs`, `redoc`, `health`, `ready`, `links`, `openapi.json`) |
| `expires_at` | datetime (ISO-8601) | optional; must include a UTC offset (naive datetimes are rejected, not silently assumed); normalized to UTC; must be in the future at creation time |

Optional request header: `Idempotency-Key` — see Edge-case decisions below.

### Output schema

Server-owned fields (never accepted as input, always set by the server):

| Field | Type | Meaning |
|---|---|---|
| `code` | string | the short code (generated or the accepted custom alias) |
| `created_at` | datetime (UTC) | set at insert time |
| `click_count` | integer | starts at 0, incremented on each redirect |

Echoed from input: `original_url`, `expires_at` (null if not supplied).

## Processing rules

| Rule | When it applies | Result |
|---|---|---|
| Auto-generate code | `custom_alias` omitted | random alphanumeric string (`secrets`, not `random`), `CODE_LENGTH` chars, regenerated on collision against the DB (bounded by `MAX_CODE_GENERATION_ATTEMPTS`) |
| Custom alias validation | `custom_alias` provided | reject with `422` if it fails format rules; reject with `409` if already in use |
| URL validation | always, on create | reject with `422` if scheme isn't `http`/`https` or length exceeds `MAX_URL_LENGTH` |
| Expiry-in-the-past check | on create | if `expires_at` is not strictly after the current time, reject with `422` |
| Expiry check | on redirect or metadata read | if `expires_at` is in the past, respond `404` (treated as gone, not distinguished from never-existed) |
| Click counting | on redirect only | increment `click_count` synchronously before responding |
| Idempotency-Key match | header present, same key + identical payload seen before | return `200` with the originally stored result (no new row created) |
| Idempotency-Key mismatch | header present, same key + different payload | reject with `409` |

## Edge-case decisions

| Case | Decision |
|---|---|
| Idempotency key | Optional `Idempotency-Key` header, not a natural ID or content hash. Same key + same payload → `200` with the stored result; same key + different payload → `409`. No header → no dedup at all (see below). Chosen over content-hashing because hashing the body would force "same URL → same code" unconditionally, contradicting the next row. |
| Duplicate URLs | Allowed when no `Idempotency-Key` is sent. Submitting the same `url` twice creates two independent short codes; there is no dedup-by-URL. |
| Timestamps/timezones | All timestamps stored and returned in UTC, ISO-8601. Naive (timezone-less) input is rejected rather than assumed to be UTC. |
| Empty results | `GET /links/{code}` and `GET /{code}` return `404` (not an empty `200`) when a code doesn't exist or has expired. `GET /links` returns `200` with an empty `items` list when nothing matches. |
| Ordering | `GET /links` orders `created_at DESC, id DESC` — the `id` tiebreaker keeps results deterministic when two rows share a timestamp. |
| Limits | `url` capped at `MAX_URL_LENGTH`; `custom_alias` capped at 30 chars; `GET /links` page size capped at `MAX_LIST_LIMIT`; no rate limit on creation (explicitly out of scope). |

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `DB_PATH` | `./data/app.db` | Filesystem path to the SQLite database file |
| `BASE_URL` | `http://localhost:8000` | Base URL used when composing the full short link in responses |
| `CODE_LENGTH` | `7` | Length of auto-generated short codes |
| `MAX_URL_LENGTH` | `2048` | Max accepted length of the submitted `url` |
| `LOG_LEVEL` | `INFO` | Application log verbosity |
| `MAX_CODE_GENERATION_ATTEMPTS` | `5` | Retry bound when a randomly generated code collides with an existing one |
| `DEFAULT_LIST_LIMIT` | `20` | Default page size for `GET /links` when `limit` isn't specified |
| `MAX_LIST_LIMIT` | `100` | Hard cap on `GET /links` page size regardless of the requested `limit` |

All values are read once at startup and validated (type/range checked); the app fails fast on an invalid config rather than falling back silently.

## Storage

SQLite, as a single file on disk at `DB_PATH`. Data survives a process restart because it's a file, not an in-memory store. It does **not** survive a redeploy on a platform with an ephemeral filesystem (e.g. a fresh App Platform container) unless `DB_PATH` points at a mounted persistent volume — this is a known trade-off of choosing SQLite over a managed Postgres instance for this build, made for setup speed within the time-boxed session.

## Setup and running locally

**Prerequisites**: Python 3.14 (see the Python-version note in Decisions & trade-offs below for why not 3.11).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env   # edit if you want non-default values
uvicorn app.main:app --reload
```

The API is then available at `http://localhost:8000` (interactive Swagger docs at `http://localhost:8000/docs`).

**Running the tests**:

```bash
ruff check .
ruff format --check .
pytest -q
```

**Running in Docker**:

```bash
docker build -t url-shortener .
docker run -p 8000:8000 -e PORT=8000 url-shortener
```

## Decisions & trade-offs

- **SQLite over Postgres**: faster to stand up with no external dependency; the repository layer is written so swapping to Postgres later is a config + driver change, not a rewrite.
- **302 over 301 redirects**: keeps every redirect hitting the server, so click counts and future expiry/deactivation logic stay accurate; a 301 risks being cached by browsers/CDNs indefinitely.
- **Synchronous click counting**: simplest correct implementation for this scale; noted as a future bottleneck under high redirect traffic (would move to async/batched increments).
- **Python 3.14 instead of the originally specified 3.11**: only 3.14 was available in this environment; the project standardizes on 3.14 throughout (local venv, Dockerfile, and CI's `actions/setup-python`), rather than keeping 3.11 as a nominal target that nothing actually runs.
- **App-level lock around the shared SQLite connection**: FastAPI runs sync `def` handlers in a thread pool, and `sqlite3.Connection` isn't safe for concurrent use from multiple threads even with `check_same_thread=False`. A `threading.Lock` held for the full duration of each check-and-write transaction makes "check + write in one transaction" actually true, not just documented.
- **Business rules split from schema validation**: format/type checks (URL scheme, alias charset/length/reserved words, timezone-awareness) live in `app/schemas.py` and need no facts beyond the input itself. Rules that need a fact from the current instant or the database (is this alias taken, is `expires_at` already in the past) live in `app/processing.py` as pure functions that take `now` and DB facts as arguments — they never call `datetime.now()` or query the DB themselves, which is what makes them unit-testable without spinning up the app.
- **Concurrent identical `Idempotency-Key` requests never 500**: `create_link` catches two distinct UNIQUE-constraint violations separately. A `links.code` collision means "try a different random code." A `idempotency_keys.key` collision means a concurrent request already committed a result for this exact key — the correct response is to fetch and return *that* committed result as a `200` replay, not to retry code generation (which found this the hard way: a flaky test run surfaced threads exhausting `MAX_CODE_GENERATION_ATTEMPTS` and returning a spurious `500` before this distinction existed).

## What I prioritized

- **Correctness under concurrency over raw performance.** The lock-per-transaction design in `store.py` trades some throughput for a guarantee: two requests can never corrupt each other's writes or see a torn read. This was validated, not assumed — see the concurrency tests and the fault-injection demo (temporarily removing the lock to confirm the tests actually fail without it).
- **A layered architecture (schemas / processing / store / handlers) over a fast, flat implementation.** It cost more time up front, but it's what made the pure `processing.py` functions unit-testable in isolation and made every business rule locatable in one obvious place.
- **An honest, fail-fast config and error surface over convenience.** Invalid config crashes at startup with a clear message instead of limping along with a bad default; unhandled exceptions return a generic `500` with a request id instead of leaking a stack trace.
- **A CI/test safety net over hand-verification.** 82 tests (unit + integration + concurrency + config), run 3x for flakiness, wired into required GitHub checks, so regressions get caught mechanically rather than relying on me remembering to re-check things by hand.

**What I explicitly did *not* optimize for**: request throughput/latency at scale, horizontal scalability, multi-tenant auth, or protecting against abuse (rate limiting). All three are real gaps for a production service — see "Known weaknesses" and "Scaling path" below — but none of them were where the time-boxed effort would pay off most for this exercise.

## What I skipped and why

Time-boxed, in the order I'd pick them back up:

1. **Deploying to DigitalOcean App Platform.** The Dockerfile and CI Docker-build check exist and are proven to work, but I never ran an actual `doctl` deploy or wired GitHub autodeploy. This was a deliberate call earlier in the session: finish core correctness + tests + CI first, attempt deploy only if time remained.
2. **Rate limiting / abuse prevention.** No protection today against someone scripting thousands of `POST /links` calls. Documented as an explicit non-goal from the start, but it's the first thing I'd add before genuinely exposing this publicly.
3. **Auth / link ownership.** Every link is anonymous and globally visible via `GET /links`; there's no concept of "whose link is this" or a way to delete/deactivate one.
4. **Postgres migration.** The store layer was written to make this a config + driver swap, not a rewrite, but the swap itself was never done — SQLite's single-writer model is the first real scaling ceiling (see below).
5. **Metrics/tracing (Prometheus, OpenTelemetry).** Only structured JSON logs exist today; no dashboards, no alerting is actually wired up (see "Operations" below for what I'd alert on).

## Trade-offs

| Decision | Chosen | Alternative | Alternative gets you | Mine gets you | When I'd switch |
|---|---|---|---|---|---|
| Storage | SQLite | Postgres | Concurrent writers via row-level MVCC locking, no single-writer ceiling | Zero external dependency, instant local setup, trivial to reason about | The moment concurrent write volume becomes real (see scaling path) |
| Processing model | Sync `def` handlers, blocking `sqlite3` driver | Async handlers + async DB driver (e.g. `aiosqlite`/`asyncpg`) | Higher concurrency per process (no thread-pool ceiling for I/O-bound work) | Simpler code, no need to audit every call for accidental blocking-in-event-loop bugs | When Postgres migration happens — pairs naturally with an async driver |
| When rules run | Write-time validation (alias/expiry checked at creation) + read-time expiry check (lazy, on access) | Fully write-time (a background job expires/deletes rows on a schedule) | Storage doesn't grow with dead rows; `GET /links` never has to filter | No background worker to run/monitor; correctness doesn't depend on a cron job firing | If storage growth or `active_only` query cost becomes measurable (see known weaknesses) |
| Abuse/quality signal | Fixed rules (URL scheme, length, reserved words) | External service (Safe Browsing API) or ML classifier | Catches malicious/spam URLs the rules can't see | No external dependency, no added latency, no third-party outage risk | If this became public-facing and link-based phishing became a real threat model |
| Pagination | `limit` + `offset` | Cursor-based (opaque token) | Stable results even if rows are inserted mid-pagination; efficient on huge offsets | Simpler to implement and to call by hand (`?offset=40`); fine at this data volume | Once a single deployment holds enough rows that `OFFSET` scans become slow (tens of millions of rows) |
| Validation strictness | Strict: `extra="forbid"`, reject naive datetimes, reject numeric-epoch coercion | Lenient: accept best-effort input, coerce where possible | Slightly friendlier to sloppy clients | Catches integration bugs at the boundary immediately instead of silently misinterpreting input (this is exactly what caught 2 of the 4 real bugs found during testing) | Rarely — this is a deliberate, durable choice for an API contract, not a time-boxed shortcut |
| Deploy gating | Branch protection (required CI checks before merge), direct push still allowed | Deploy-from-Actions (a `deploy` job gated on `needs: [test, docker]`) | Deploy itself becomes an explicit, logged pipeline stage; easy to add manual-approval gates later | No secrets to manage, no second failure surface, achieves the same "broken code never reaches main" goal today | Once there's a real need: multiple environments, a required manual approval, or deploy-time steps (migrations) CI must gate |

## Known weaknesses / failure modes

- **SQLite's single-writer lock is a latency bottleneck under load, not a correctness bug.** We proved correctness holds (concurrency tests + fault-injection demo), but every write across the whole process is serialized — at real concurrent load this shows up as increased tail latency, not wrong answers.
- **Expired links are never reclaimed.** There's no cleanup job, so an alias used by an expired link stays "taken" forever — nobody can ever reuse that custom alias, even though the link itself is functionally dead. This is a real product gap, not just a storage one.
- **Unbounded growth of `links` and `idempotency_keys`.** Neither table is ever pruned. Over a long enough time horizon this is both a storage-growth and a query-performance problem.
- **Click counts have no bot/scraper filtering.** A crawler or link-preview bot hitting a short link inflates `click_count` just like a real user would — this is a false positive in the metadata, not a bug, but worth knowing before trusting the number for anything analytics-facing.
- **No rate limiting.** Nothing stops a single client from creating an unbounded number of links or hammering a redirect endpoint.
- **No CORS configuration.** If a browser-based frontend ever calls this API directly (rather than server-to-server), cross-origin requests will fail until CORS middleware is added.
- **Reserved-alias list is a manual, easy-to-forget list.** Adding a new top-level route later (e.g. `/admin`) without also adding it to `RESERVED_ALIASES` in `app/schemas.py` would let a user "shadow" that route with a custom alias.

## Operations

- **Config**: see the Configuration table above — every tunable is an env var, validated at startup, fails fast with a clear message on an invalid value.
- **Health vs readiness**: `/health` is liveness (process is up, no dependencies checked); `/ready` runs `SELECT 1` against the live DB connection and returns `503` if it fails — this is what should gate whether an orchestrator routes traffic to this instance.
- **Logs**: structured JSON, one line per request (method, path, status, duration_ms, request_id) plus one line per business decision (alias_taken, link_created, redirect, etc.), all carrying the same request id so a single request's full story is traceable by grepping one value. No user-submitted URLs or other content are ever logged.
- **Metrics — the honest gap**: there is no metrics or tracing library wired up today (no Prometheus, no OpenTelemetry); observability is logs-only. If I were adding alerting next, I'd alert on:
  - 5xx rate > 0 sustained for more than a minute (should be near-zero given the generic error handler)
  - `/ready` returning 503 for more than one health-check interval (DB unreachable)
  - Redirect 404 rate spiking (could mean a bad deploy, a bug, or link-scanning abuse)
  - p99 request latency crossing a threshold (early signal of the SQLite lock contention described above)
  - Idempotency-Key conflict rate spiking (usually indicates a client-side bug reusing keys incorrectly)
  - `DB_PATH` file size growth rate (early warning for the unbounded-growth weakness above)

## Scaling path

Ordered by what would actually break first in this architecture, with the fix for each:

1. **SQLite write serialization** — first ceiling under concurrent creates/redirects, since every write (and now every read, per the correctness fix) holds one process-wide lock. *Fix*: migrate to Postgres; the store layer was written so this is a driver + connection-string change, not a rewrite.
2. **Single-instance ceiling** — even after a Postgres migration, this app can't run as multiple replicas yet, because the in-process lock only serializes access within one process, not across processes. *Fix*: once on Postgres, the database itself becomes the source of truth for concurrency control (via constraints/row locks), so multiple stateless app instances can run behind a load balancer.
3. **Unbounded storage growth** — `links` and `idempotency_keys` grow forever. *Fix*: a scheduled cleanup job that deletes expired links and old idempotency records past some retention window.
4. **No read cache on hot redirects** — every single redirect is a DB round-trip. *Fix*: add a read-through cache (e.g. Redis) in front of the code→URL lookup for frequently hit codes.
5. **No abuse protection** — becomes a real problem once this is reachable by anyone. *Fix*: rate limiting middleware or an API gateway in front of the service.
6. **Click-counter write contention** — at very high redirect volume, the synchronous increment on every redirect becomes a hot row. *Fix*: move to async/batched increments (a queue that periodically flushes aggregated counts).
7. **Single region** — eventually, latency for geographically distant users. *Fix*: multi-region deployment with a globally distributed database or read replicas — the last problem to solve, not the first.

## Live URL, running locally, and CI

- **Live URL**: not deployed. Deployment to DigitalOcean App Platform was scoped as a stretch goal and wasn't picked up in this session — see "What I skipped and why" above.
- **Running locally**: see "Setup and running locally" above.
- **CI**: see `.github/workflows/ci.yml` — on every push/PR to `main`, a `test` job (lint, format check, `pytest -q` on Python 3.14) and a `docker` job (`docker build .`) both run; `main` requires both to pass via branch protection before a PR can merge.
