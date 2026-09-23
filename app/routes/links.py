import hashlib
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import RedirectResponse
from starlette.requests import Request

from app import processing, store
from app.codegen import generate_candidate_code
from app.config import settings
from app.db import get_connection, get_lock
from app.middleware import get_request_id
from app.schemas import LinkCreateRequest, LinkListResponse, LinkResponse

logger = logging.getLogger("app.processing")

router = APIRouter()
redirect_router = APIRouter()

IDEMPOTENCY_HEADER = "Idempotency-Key"


def _hash_payload(payload: LinkCreateRequest) -> str:
    data = payload.model_dump(mode="json")
    canonical = json.dumps(data, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _to_response(link: store.LinkRow) -> LinkResponse:
    return LinkResponse(
        code=link.code,
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        click_count=link.click_count,
    )


def _log(event: str, **fields) -> None:
    logger.info(event, extra={"extra_fields": {"request_id": get_request_id(), **fields}})


@router.post("/links", response_model=LinkResponse, status_code=201)
def create_link(payload: LinkCreateRequest, request: Request, response: Response):
    conn = get_connection()
    lock = get_lock()
    now = datetime.now(timezone.utc)
    request_hash = _hash_payload(payload)

    idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
    if idempotency_key is not None:
        existing = store.get_idempotency_record(conn, idempotency_key)
        decision = processing.decide_idempotency(
            existing_hash=existing.request_hash if existing else None,
            existing_code=existing.code if existing else None,
            request_hash=request_hash,
        )
        if decision.outcome is processing.IdempotencyOutcome.REPLAY:
            link = store.get_link_by_code(conn, decision.code)
            _log("link_create_replay", code=decision.code)
            response.status_code = 200
            return _to_response(link)
        if decision.outcome is processing.IdempotencyOutcome.CONFLICT:
            _log("idempotency_key_conflict", idempotency_key=idempotency_key)
            raise HTTPException(
                status_code=409, detail="Idempotency-Key reused with a different payload"
            )

    alias_taken = False
    if payload.custom_alias is not None:
        alias_taken = store.get_link_by_code(conn, payload.custom_alias) is not None

    create_decision = processing.decide_create_link(
        custom_alias=payload.custom_alias,
        alias_taken=alias_taken,
        expires_at=payload.expires_at,
        now=now,
    )

    if create_decision.outcome is processing.CreateOutcome.ALIAS_TAKEN:
        _log("alias_taken", alias=payload.custom_alias)
        raise HTTPException(status_code=409, detail="custom_alias is already in use")
    if create_decision.outcome is processing.CreateOutcome.EXPIRES_IN_PAST:
        _log("expires_in_past")
        raise HTTPException(status_code=422, detail="expires_at must be in the future")

    if create_decision.code is not None:
        link = store.create_link(
            conn,
            lock,
            code=create_decision.code,
            original_url=payload.url,
            created_at=now,
            expires_at=payload.expires_at,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
    else:
        link = None
        last_error: Exception | None = None
        for _ in range(settings.max_code_generation_attempts):
            candidate = generate_candidate_code(settings.code_length)
            try:
                link = store.create_link(
                    conn,
                    lock,
                    code=candidate,
                    original_url=payload.url,
                    created_at=now,
                    expires_at=payload.expires_at,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                )
                break
            except store.CodeTakenError as exc:
                last_error = exc
                continue
        if link is None:
            _log("code_generation_exhausted")
            raise HTTPException(
                status_code=500, detail="Could not allocate a short code"
            ) from last_error

    _log("link_created", code=link.code)
    return _to_response(link)


@router.get("/links", response_model=LinkListResponse)
def list_links(
    active_only: bool = False,
    limit: int | None = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
):
    conn = get_connection()
    now = datetime.now(timezone.utc)
    effective_limit = min(limit or settings.default_list_limit, settings.max_list_limit)

    links = store.list_links(
        conn, active_only=active_only, now=now, limit=effective_limit, offset=offset
    )
    _log(
        "list_links",
        count=len(links),
        active_only=active_only,
        limit=effective_limit,
        offset=offset,
    )
    return LinkListResponse(
        items=[_to_response(link) for link in links],
        limit=effective_limit,
        offset=offset,
    )


@router.get("/links/{code}", response_model=LinkResponse)
def get_link_metadata(code: str):
    conn = get_connection()
    now = datetime.now(timezone.utc)
    link = store.get_link_by_code(conn, code)
    if link is None or processing.is_expired(link.expires_at, now):
        _log("metadata_lookup_miss", code=code)
        raise HTTPException(status_code=404, detail="short link not found")
    _log("metadata_lookup", code=code)
    return _to_response(link)


@redirect_router.get("/{code}")
def redirect_to_original(code: str):
    conn = get_connection()
    lock = get_lock()
    now = datetime.now(timezone.utc)
    link = store.get_link_by_code(conn, code)
    if link is None or processing.is_expired(link.expires_at, now):
        _log("redirect_miss", code=code)
        raise HTTPException(status_code=404, detail="short link not found")
    store.increment_click(conn, lock, code)
    _log("redirect", code=code)
    return RedirectResponse(url=link.original_url, status_code=302)
