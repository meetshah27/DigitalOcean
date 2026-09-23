# URL Shortener API

![CI](https://github.com/meetshah27/DigitalOcean/actions/workflows/ci.yml/badge.svg)

A production-ready REST API that shortens long URLs, redirects short codes to
their original URL, and returns metadata about created links.

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
| `POST` | `/links` | `201 Created` | `400` invalid URL/alias, `409` alias already taken |
| `GET` | `/{code}` | `302 Found` (redirect) | `404` not found or expired |
| `GET` | `/links/{code}` | `200 OK` | `404` not found or expired |

### Input schema (`POST /links`)

| Field | Type | Validation rule |
|---|---|---|
| `url` | string | required; must parse as `http`/`https`; max length 2048 |
| `custom_alias` | string | optional; 3–30 chars; `[A-Za-z0-9_-]` only; case-sensitive; rejected if it matches a reserved word (`api`, `docs`, `health`, `links`) |
| `expires_at` | datetime (ISO-8601, UTC) | optional; must be in the future at creation time |

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
| Auto-generate code | `custom_alias` omitted | random base62 string, 7 chars, regenerated on collision against the DB |
| Custom alias validation | `custom_alias` provided | reject with `400` if it fails format rules; reject with `409` if already in use |
| URL validation | always, on create | reject with `400` if scheme isn't `http`/`https` or length exceeds 2048 |
| Expiry check | on redirect or metadata read | if `expires_at` is in the past, respond `404` (treated as gone, not distinguished from never-existed) |
| Click counting | on redirect only | increment `click_count` synchronously before responding |

## Edge-case decisions

| Case | Decision |
|---|---|
| Idempotency key | None. No `Idempotency-Key` header is supported; this is a deliberate scope cut, not an oversight. |
| Duplicate URLs | Allowed. Submitting the same `url` twice creates two independent short codes; there is no dedup-by-URL. |
| Timestamps/timezones | All timestamps stored and returned in UTC, ISO-8601 (`...Z`). No local-timezone conversion is performed server-side. |
| Empty results | `GET /links/{code}` and `GET /{code}` return `404` (not an empty `200`) when a code doesn't exist or has expired. |
| Ordering | Not applicable — there is no list/collection endpoint in this API, only single-resource lookups by code. |
| Limits | `url` capped at 2048 chars; `custom_alias` capped at 30 chars; no rate limit on creation (explicitly out of scope). |

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `DB_PATH` | `./data/app.db` | Filesystem path to the SQLite database file |
| `BASE_URL` | `http://localhost:8000` | Base URL used when composing the full short link in responses |
| `CODE_LENGTH` | `7` | Length of auto-generated short codes |
| `MAX_URL_LENGTH` | `2048` | Max accepted length of the submitted `url` |
| `LOG_LEVEL` | `INFO` | Application log verbosity |

All values are read once at startup and validated (type/range checked); the app fails fast on an invalid config rather than falling back silently.

## Storage

SQLite, as a single file on disk at `DB_PATH`. Data survives a process restart because it's a file, not an in-memory store. It does **not** survive a redeploy on a platform with an ephemeral filesystem (e.g. a fresh App Platform container) unless `DB_PATH` points at a mounted persistent volume — this is a known trade-off of choosing SQLite over a managed Postgres instance for this build, made for setup speed within the time-boxed session.

## Decisions & trade-offs

- **SQLite over Postgres**: faster to stand up with no external dependency; the repository layer is written so swapping to Postgres later is a config + driver change, not a rewrite.
- **302 over 301 redirects**: keeps every redirect hitting the server, so click counts and future expiry/deactivation logic stay accurate; a 301 risks being cached by browsers/CDNs indefinitely.
- **Synchronous click counting**: simplest correct implementation for this scale; noted as a future bottleneck under high redirect traffic (would move to async/batched increments).
- **Python 3.14 instead of the originally specified 3.11**: only 3.14 was available in this environment; no code in this stack relies on 3.11-specific behavior.
