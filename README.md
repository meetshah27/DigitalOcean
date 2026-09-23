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

## Decisions & trade-offs

- **SQLite over Postgres**: faster to stand up with no external dependency; the repository layer is written so swapping to Postgres later is a config + driver change, not a rewrite.
- **302 over 301 redirects**: keeps every redirect hitting the server, so click counts and future expiry/deactivation logic stay accurate; a 301 risks being cached by browsers/CDNs indefinitely.
- **Synchronous click counting**: simplest correct implementation for this scale; noted as a future bottleneck under high redirect traffic (would move to async/batched increments).
- **Python 3.14 instead of the originally specified 3.11**: only 3.14 was available in this environment; the project standardizes on 3.14 throughout (local venv, Dockerfile, and CI's `actions/setup-python`), rather than keeping 3.11 as a nominal target that nothing actually runs.
- **App-level lock around the shared SQLite connection**: FastAPI runs sync `def` handlers in a thread pool, and `sqlite3.Connection` isn't safe for concurrent use from multiple threads even with `check_same_thread=False`. A `threading.Lock` held for the full duration of each check-and-write transaction makes "check + write in one transaction" actually true, not just documented.
- **Business rules split from schema validation**: format/type checks (URL scheme, alias charset/length/reserved words, timezone-awareness) live in `app/schemas.py` and need no facts beyond the input itself. Rules that need a fact from the current instant or the database (is this alias taken, is `expires_at` already in the past) live in `app/processing.py` as pure functions that take `now` and DB facts as arguments — they never call `datetime.now()` or query the DB themselves, which is what makes them unit-testable without spinning up the app.
- **Concurrent identical `Idempotency-Key` requests never 500**: `create_link` catches two distinct UNIQUE-constraint violations separately. A `links.code` collision means "try a different random code." A `idempotency_keys.key` collision means a concurrent request already committed a result for this exact key — the correct response is to fetch and return *that* committed result as a `200` replay, not to retry code generation (which found this the hard way: a flaky test run surfaced threads exhausting `MAX_CODE_GENERATION_ATTEMPTS` and returning a spurious `500` before this distinction existed).
