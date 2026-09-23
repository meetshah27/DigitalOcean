def test_unicode_domain_and_path_in_url_is_accepted(client):
    response = client.post(
        "/links", json={"url": "https://xn--e28h.jp/%E3%83%9A%E3%83%BC%E3%82%B8"}
    )
    assert response.status_code == 201


def test_emoji_in_url_path_is_accepted(client):
    response = client.post("/links", json={"url": "https://example.com/\U0001f600"})
    assert response.status_code == 201


def test_emoji_in_custom_alias_is_rejected(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "custom_alias": "abc\U0001f600"}
    )
    assert response.status_code == 422


def test_accented_characters_in_custom_alias_are_rejected(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "custom_alias": "cafe-links-e9"}
    )
    assert response.status_code == 201  # sanity: plain ascii equivalent is fine

    response = client.post(
        "/links", json={"url": "https://example.com/b", "custom_alias": "café-links"}
    )
    assert response.status_code == 422


def test_whitespace_only_url_is_rejected(client):
    response = client.post("/links", json={"url": "   "})
    assert response.status_code == 422


def test_whitespace_only_custom_alias_is_rejected(client):
    response = client.post("/links", json={"url": "https://example.com/a", "custom_alias": "   "})
    assert response.status_code == 422


def test_custom_alias_with_internal_whitespace_is_rejected(client):
    response = client.post(
        "/links", json={"url": "https://example.com/a", "custom_alias": "my alias"}
    )
    assert response.status_code == 422
