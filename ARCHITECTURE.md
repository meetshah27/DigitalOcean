# Architecture

High-level view of the request lifecycle and data flow for the URL Shortener API.
See [README.md](README.md) for the full API spec, configuration, and design decisions.

## Component / data-flow overview

```mermaid
flowchart TD
    Client([Client])

    subgraph App["FastAPI app (app/main.py)"]
        MW["RequestContextMiddleware\n(request-id, timing, JSON access log)"]
        Router["Routers, in registration order:\nhealth -> links -> redirect (/{code} catch-all last)"]
        Schemas["schemas.py\nedge validation: types, bounds,\nextra=forbid, timezone-aware datetimes"]
        Processing["processing.py\npure decision functions\n(no I/O, no clock — now() and\nDB facts passed in as arguments)"]
        Store["store.py\nSQLite via one shared connection,\nevery access under threading.Lock,\ncheck+write in one transaction"]
        ErrorHandler["errors.py\ngeneric 500 + request id\n(real exception only in logs)"]
    end

    Config["config.py\nenv vars validated once at startup,\nfails fast on invalid config"]
    DB[(SQLite file\nDB_PATH)]
    Logs[/"Structured JSON logs\n(stdout)"/]

    Client -->|HTTP request| MW --> Router --> Schemas --> Processing --> Store --> DB
    Store -.->|LinkRow| Router
    Router -->|HTTP response, X-Request-ID header| Client
    Router -.->|domain error| ErrorHandler -.-> Client
    Config -.->|settings singleton, loaded once| App
    MW -.-> Logs
    Processing -.-> Logs
    ErrorHandler -.-> Logs
```

**What this shows**: every request passes through the same middleware (request-id + logging) regardless of outcome, then edge validation, then business rules, then persistence — each layer only depends on the one below it. `processing.py` never touches the database or the clock directly, which is what makes its decisions unit-testable in isolation (see `tests/test_processing.py`). Config is loaded exactly once at process startup and handed to every layer that needs it; nothing re-reads the environment mid-request.

## Request lifecycle: `POST /links`

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as Middleware
    participant H as Handler (routes/links.py)
    participant S as schemas.py
    participant P as processing.py
    participant St as store.py (SQLite + lock)

    C->>MW: POST /links {url, custom_alias?, expires_at?}
    MW->>MW: assign/echo X-Request-ID
    MW->>H: forward request
    H->>S: parse + validate body
    alt invalid (bad type, bad url, bad alias, naive datetime, extra field)
        S-->>H: 422 Unprocessable Entity
    else valid
        opt Idempotency-Key header present
            H->>St: get_idempotency_record(key)
            St-->>H: existing hash/code, or none
            H->>P: decide_idempotency(existing, request_hash)
            alt same key + same payload (REPLAY)
                P-->>H: replay decision
                H->>St: get_link_by_code(stored code)
                H-->>C: 200 OK (stored result)
            else same key + different payload (CONFLICT)
                P-->>H: conflict decision
                H-->>C: 409 Conflict
            end
        end
        H->>St: get_link_by_code(custom_alias) [if provided]
        H->>P: decide_create_link(alias_taken, expires_at, now)
        alt expires_at in the past
            P-->>H: EXPIRES_IN_PAST
            H-->>C: 422 Unprocessable Entity
        else alias already taken
            P-->>H: ALIAS_TAKEN
            H-->>C: 409 Conflict
        else OK
            H->>St: create_link(code or random candidate)
            alt UNIQUE violation on links.code
                St-->>H: CodeTakenError
                H->>H: retry with a new random code (bounded)
            else UNIQUE violation on idempotency_keys.key
                St-->>H: IdempotencyKeyRaceError
                H->>St: fetch the concurrent winner's committed result
                H-->>C: 200 OK (winner's result, not a new row)
            else success
                St-->>H: LinkRow
                H-->>C: 201 Created {code, original_url, created_at, expires_at, click_count}
            end
        end
    end
```

**What this shows**: validation happens before any business rule is evaluated, business rules (alias/expiry) are evaluated before any write is attempted, and the two ways a concurrent write can fail (`CodeTakenError` vs `IdempotencyKeyRaceError`) are handled differently — one retries, the other fetches and returns the already-committed result instead of retrying something that can never succeed. This distinction was the fourth bug found during edge-case testing (see the "Decisions & trade-offs" section of the README).

## Request lifecycle: `GET /{code}` (redirect)

```mermaid
sequenceDiagram
    participant C as Client
    participant MW as Middleware
    participant H as Handler (redirect_to_original)
    participant P as processing.py
    participant St as store.py

    C->>MW: GET /{code}
    MW->>H: forward request
    H->>St: get_link_by_code(code)
    alt not found
        St-->>H: None
        H-->>C: 404 Not Found
    else found
        St-->>H: LinkRow
        H->>P: is_expired(expires_at, now)
        alt expired
            P-->>H: true
            H-->>C: 404 Not Found (treated as gone, not distinguished from never-existed)
        else active
            H->>St: increment_click(code)
            H-->>C: 302 Found, Location: original_url
        end
    end
```

**What this shows**: the redirect is intentionally a `302` (not `301`) so every hit reaches this handler — that's what makes click counting and future expiry checks reliable, instead of a browser or CDN caching the redirect and skipping the server entirely.
