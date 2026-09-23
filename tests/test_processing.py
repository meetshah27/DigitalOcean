from datetime import datetime, timedelta, timezone

from app.processing import (
    CreateOutcome,
    IdempotencyOutcome,
    decide_create_link,
    decide_idempotency,
    is_expired,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_decide_create_link_ok_without_alias():
    decision = decide_create_link(custom_alias=None, alias_taken=False, expires_at=None, now=NOW)
    assert decision.outcome is CreateOutcome.OK
    assert decision.code is None


def test_decide_create_link_ok_with_free_alias():
    decision = decide_create_link(
        custom_alias="my-alias", alias_taken=False, expires_at=None, now=NOW
    )
    assert decision.outcome is CreateOutcome.OK
    assert decision.code == "my-alias"


def test_decide_create_link_alias_taken():
    decision = decide_create_link(
        custom_alias="my-alias", alias_taken=True, expires_at=None, now=NOW
    )
    assert decision.outcome is CreateOutcome.ALIAS_TAKEN


def test_decide_create_link_expires_in_past():
    decision = decide_create_link(
        custom_alias=None, alias_taken=False, expires_at=NOW - timedelta(seconds=1), now=NOW
    )
    assert decision.outcome is CreateOutcome.EXPIRES_IN_PAST


def test_decide_create_link_expires_exactly_now_is_rejected():
    decision = decide_create_link(custom_alias=None, alias_taken=False, expires_at=NOW, now=NOW)
    assert decision.outcome is CreateOutcome.EXPIRES_IN_PAST


def test_decide_create_link_expiry_checked_before_alias():
    decision = decide_create_link(
        custom_alias="taken", alias_taken=True, expires_at=NOW - timedelta(seconds=1), now=NOW
    )
    assert decision.outcome is CreateOutcome.EXPIRES_IN_PAST


def test_is_expired_none_never_expires():
    assert is_expired(None, NOW) is False


def test_is_expired_future_is_not_expired():
    assert is_expired(NOW + timedelta(seconds=1), NOW) is False


def test_is_expired_past_is_expired():
    assert is_expired(NOW - timedelta(seconds=1), NOW) is True


def test_decide_idempotency_new_when_no_existing_record():
    decision = decide_idempotency(existing_hash=None, existing_code=None, request_hash="abc")
    assert decision.outcome is IdempotencyOutcome.NEW


def test_decide_idempotency_replay_when_hash_matches():
    decision = decide_idempotency(existing_hash="abc", existing_code="xyz123", request_hash="abc")
    assert decision.outcome is IdempotencyOutcome.REPLAY
    assert decision.code == "xyz123"


def test_decide_idempotency_conflict_when_hash_differs():
    decision = decide_idempotency(existing_hash="abc", existing_code="xyz123", request_hash="def")
    assert decision.outcome is IdempotencyOutcome.CONFLICT
