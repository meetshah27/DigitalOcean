from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class CreateOutcome(str, Enum):
    OK = "ok"
    ALIAS_TAKEN = "alias_taken"
    EXPIRES_IN_PAST = "expires_in_past"


@dataclass(frozen=True)
class CreateDecision:
    outcome: CreateOutcome
    code: str | None  # the alias to use, or None meaning "generate a random one"


def decide_create_link(
    *,
    custom_alias: str | None,
    alias_taken: bool,
    expires_at: datetime | None,
    now: datetime,
) -> CreateDecision:
    if expires_at is not None and expires_at <= now:
        return CreateDecision(CreateOutcome.EXPIRES_IN_PAST, None)
    if custom_alias is not None and alias_taken:
        return CreateDecision(CreateOutcome.ALIAS_TAKEN, None)
    return CreateDecision(CreateOutcome.OK, custom_alias)


def is_expired(expires_at: datetime | None, now: datetime) -> bool:
    return expires_at is not None and expires_at <= now


class IdempotencyOutcome(str, Enum):
    NEW = "new"
    REPLAY = "replay"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class IdempotencyDecision:
    outcome: IdempotencyOutcome
    code: str | None  # the previously stored code, only set on REPLAY


def decide_idempotency(
    *,
    existing_hash: str | None,
    existing_code: str | None,
    request_hash: str,
) -> IdempotencyDecision:
    if existing_hash is None:
        return IdempotencyDecision(IdempotencyOutcome.NEW, None)
    if existing_hash == request_hash:
        return IdempotencyDecision(IdempotencyOutcome.REPLAY, existing_code)
    return IdempotencyDecision(IdempotencyOutcome.CONFLICT, None)
