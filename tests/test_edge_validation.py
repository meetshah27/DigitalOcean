from app.config import settings


def test_missing_url_is_rejected(client):
    response = client.post("/links", json={})
    assert response.status_code == 422


def test_url_wrong_type_is_rejected(client):
    response = client.post("/links", json={"url": 12345})
    assert response.status_code == 422


def test_custom_alias_wrong_type_is_rejected(client):
    response = client.post("/links", json={"url": "https://example.com/a", "custom_alias": 123})
    assert response.status_code == 422


def test_custom_alias_too_short_is_rejected(client):
    response = client.post("/links", json={"url": "https://example.com/a", "custom_alias": "ab"})
    assert response.status_code == 422


def test_custom_alias_too_long_is_rejected(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "custom_alias": "a" * 31}
    )
    assert response.status_code == 422


def test_custom_alias_min_length_boundary_is_accepted(client):
    response = client.post("/links", json={"url": "https://example.com/a", "custom_alias": "abc"})
    assert response.status_code == 201


def test_custom_alias_max_length_boundary_is_accepted(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "custom_alias": "a" * 30}
    )
    assert response.status_code == 201


def test_url_at_max_length_boundary_is_accepted(client):
    padding = "a" * (settings.max_url_length - len("https://example.com/"))
    url = f"https://example.com/{padding}"
    assert len(url) == settings.max_url_length
    response = client.post("/links", json={"url": url})
    assert response.status_code == 201


def test_url_over_max_length_is_rejected(client):
    padding = "a" * (settings.max_url_length - len("https://example.com/") + 1)
    url = f"https://example.com/{padding}"
    assert len(url) == settings.max_url_length + 1
    response = client.post("/links", json={"url": url})
    assert response.status_code == 422


def test_extra_unknown_field_is_rejected(client):
    response = client.post("/links", json={"url": "https://example.com/a", "extra": "nope"})
    assert response.status_code == 422


def test_malformed_json_body_is_rejected(client):
    response = client.post(
        "/links",
        content=b'{"url": "https://example.com/a"',
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422


def test_json_array_body_is_rejected(client):
    response = client.post("/links", content=b"[]", headers={"Content-Type": "application/json"})
    assert response.status_code == 422


def test_json_string_body_is_rejected(client):
    response = client.post(
        "/links", content=b'"just a string"', headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
