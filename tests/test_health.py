import uuid

from app.main import app


def test_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_200_when_db_reachable(client):
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_returns_503_when_db_unreachable(client, monkeypatch):
    monkeypatch.setattr("app.routes.health.is_ready", lambda: False)
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}


def test_request_id_is_generated_when_absent(client):
    response = client.get("/health")
    request_id = response.headers.get("X-Request-ID")
    assert request_id
    uuid.UUID(request_id)


def test_request_id_is_echoed_when_provided(client):
    custom_id = "my-custom-request-id"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.headers.get("X-Request-ID") == custom_id


def test_unhandled_exception_returns_generic_500_with_request_id(client):
    # Two path segments so this doesn't get shadowed by the /{code} redirect catch-all,
    # which only matches a single segment and is registered ahead of routes added here.
    @app.get("/__test__/boom")
    async def boom():
        raise RuntimeError("boom")

    response = client.get("/__test__/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "internal_error"
    assert body["request_id"] == response.headers.get("X-Request-ID")
