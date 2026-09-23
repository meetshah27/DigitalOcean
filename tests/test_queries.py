from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import get_connection, get_lock
from app.store import create_link as store_create_link


def test_limit_zero_is_rejected(client):
    response = client.get("/links", params={"limit": 0})
    assert response.status_code == 422


def test_negative_offset_is_rejected(client):
    response = client.get("/links", params={"offset": -1})
    assert response.status_code == 422


def test_limit_above_max_is_silently_capped(client):
    response = client.get("/links", params={"limit": settings.max_list_limit + 500})
    assert response.status_code == 200
    assert response.json()["limit"] == settings.max_list_limit


def test_offset_past_end_returns_empty_items(client):
    client.post("/links", json={"url": "https://example.com/only-one"})
    response = client.get("/links", params={"offset": 10_000, "limit": 5})
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_no_matching_rows_returns_empty_list_not_error(client):
    response = client.get("/links", params={"active_only": True, "limit": 1})
    assert response.status_code == 200
    assert isinstance(response.json()["items"], list)


def test_ordering_tiebreak_on_identical_created_at(client):
    conn = get_connection()
    lock = get_lock()
    same_instant = datetime.now(timezone.utc)

    store_create_link(
        conn,
        lock,
        code="tie-first",
        original_url="https://example.com/tie-first",
        created_at=same_instant,
        expires_at=None,
    )
    store_create_link(
        conn,
        lock,
        code="tie-second",
        original_url="https://example.com/tie-second",
        created_at=same_instant,
        expires_at=None,
    )

    response = client.get("/links", params={"limit": 2})
    codes = [item["code"] for item in response.json()["items"]]
    assert codes == ["tie-second", "tie-first"]


def test_active_only_keeps_no_expiry_and_future_expiry_rows(client):
    conn = get_connection()
    lock = get_lock()
    now = datetime.now(timezone.utc)

    store_create_link(
        conn,
        lock,
        code="filter-no-expiry",
        original_url="https://example.com/no-expiry",
        created_at=now,
        expires_at=None,
    )
    store_create_link(
        conn,
        lock,
        code="filter-future",
        original_url="https://example.com/future",
        created_at=now,
        expires_at=now + timedelta(days=1),
    )
    store_create_link(
        conn,
        lock,
        code="filter-past",
        original_url="https://example.com/past",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )

    response = client.get("/links", params={"active_only": True, "limit": 50})
    codes = {item["code"] for item in response.json()["items"]}
    assert "filter-no-expiry" in codes
    assert "filter-future" in codes
    assert "filter-past" not in codes
