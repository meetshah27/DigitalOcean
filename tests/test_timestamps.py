from datetime import datetime, timedelta, timezone


def test_naive_datetime_is_rejected(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "expires_at": "2099-01-01T00:00:00"}
    )
    assert response.status_code == 422


def test_future_utc_offset_is_accepted(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "expires_at": "2099-01-01T00:00:00+00:00"}
    )
    assert response.status_code == 201


def test_non_utc_offset_is_normalized_to_utc(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "expires_at": "2099-01-01T10:00:00+05:30"}
    )
    assert response.status_code == 201
    stored = response.json()["expires_at"]
    parsed = datetime.fromisoformat(stored)
    assert parsed.astimezone(timezone.utc) == datetime(2099, 1, 1, 4, 30, tzinfo=timezone.utc)


def test_z_suffix_offset_is_accepted(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "expires_at": "2099-01-01T00:00:00Z"}
    )
    assert response.status_code == 201


def test_numeric_epoch_timestamp_is_rejected(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "expires_at": 4102444800}
    )
    assert response.status_code == 422


def test_expiry_far_in_the_past_is_rejected(client):
    past = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    response = client.post("/links", json={"url": "https://example.com/a", "expires_at": past})
    assert response.status_code == 422


def test_expiry_one_second_in_the_future_is_accepted(client):
    future = (datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat()
    response = client.post("/links", json={"url": "https://example.com/a", "expires_at": future})
    assert response.status_code == 201
