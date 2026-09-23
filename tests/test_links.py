from datetime import datetime, timedelta, timezone

from app.db import get_connection, get_lock
from app.store import create_link as store_create_link


def test_create_with_auto_generated_code(client):
    response = client.post("/links", json={"url": "https://example.com/a"})
    assert response.status_code == 201
    body = response.json()
    assert body["original_url"] == "https://example.com/a"
    assert body["click_count"] == 0
    assert body["expires_at"] is None
    assert len(body["code"]) == 7


def test_create_with_custom_alias(client):
    response = client.post(
        "/links", json={"url": "https://example.com/b", "custom_alias": "my-alias"}
    )
    assert response.status_code == 201
    assert response.json()["code"] == "my-alias"


def test_create_with_taken_alias_returns_409(client):
    client.post("/links", json={"url": "https://example.com/c", "custom_alias": "dup-alias"})
    response = client.post(
        "/links", json={"url": "https://example.com/d", "custom_alias": "dup-alias"}
    )
    assert response.status_code == 409


def test_duplicate_url_without_idempotency_key_creates_two_codes(client):
    first = client.post("/links", json={"url": "https://example.com/same"})
    second = client.post("/links", json={"url": "https://example.com/same"})
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["code"] != second.json()["code"]


def test_create_rejects_non_http_scheme(client):
    response = client.post("/links", json={"url": "ftp://example.com/a"})
    assert response.status_code == 422


def test_create_rejects_reserved_alias(client):
    response = client.post("/links", json={"url": "https://example.com/a", "custom_alias": "api"})
    assert response.status_code == 422


def test_create_rejects_unknown_field(client):
    response = client.post("/links", json={"url": "https://example.com/a", "nope": "x"})
    assert response.status_code == 422


def test_create_rejects_naive_datetime(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "expires_at": "2099-01-01T00:00:00"}
    )
    assert response.status_code == 422


def test_create_rejects_expiry_in_the_past(client):
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = client.post("/links", json={"url": "https://example.com/a", "expires_at": past})
    assert response.status_code == 422


def test_idempotency_replay_returns_200_with_same_body(client):
    payload = {"url": "https://example.com/idempotent"}
    headers = {"Idempotency-Key": "key-1"}
    first = client.post("/links", json=payload, headers=headers)
    second = client.post("/links", json=payload, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["code"] == second.json()["code"]


def test_idempotency_conflict_on_different_payload(client):
    headers = {"Idempotency-Key": "key-2"}
    client.post("/links", json={"url": "https://example.com/one"}, headers=headers)
    response = client.post("/links", json={"url": "https://example.com/two"}, headers=headers)
    assert response.status_code == 409


def test_redirect_returns_302_and_increments_click_count(client):
    create = client.post("/links", json={"url": "https://example.com/redirect-me"})
    code = create.json()["code"]

    redirect = client.get(f"/{code}", follow_redirects=False)
    assert redirect.status_code == 302
    assert redirect.headers["location"] == "https://example.com/redirect-me"

    client.get(f"/{code}", follow_redirects=False)
    metadata = client.get(f"/links/{code}")
    assert metadata.json()["click_count"] == 2


def test_redirect_unknown_code_returns_404(client):
    response = client.get("/does-not-exist", follow_redirects=False)
    assert response.status_code == 404


def test_metadata_unknown_code_returns_404(client):
    response = client.get("/links/does-not-exist")
    assert response.status_code == 404


def test_expired_link_returns_404_on_redirect_and_metadata(client):
    conn = get_connection()
    lock = get_lock()
    now = datetime.now(timezone.utc)
    store_create_link(
        conn,
        lock,
        code="expired-one",
        original_url="https://example.com/gone",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )

    assert client.get("/expired-one", follow_redirects=False).status_code == 404
    assert client.get("/links/expired-one").status_code == 404


def test_list_links_orders_newest_first_and_respects_limit(client):
    for i in range(3):
        client.post("/links", json={"url": f"https://example.com/list-{i}"})

    response = client.get("/links", params={"limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 2
    assert len(body["items"]) == 2
    created_ats = [item["created_at"] for item in body["items"]]
    assert created_ats == sorted(created_ats, reverse=True)


def test_list_links_active_only_excludes_expired(client):
    conn = get_connection()
    lock = get_lock()
    now = datetime.now(timezone.utc)
    store_create_link(
        conn,
        lock,
        code="active-filter-expired",
        original_url="https://example.com/expired",
        created_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    client.post("/links", json={"url": "https://example.com/active-filter-live"})

    response = client.get("/links", params={"active_only": True, "limit": 50})
    codes = [item["code"] for item in response.json()["items"]]
    assert "active-filter-expired" not in codes
