def test_identical_retry_three_times_stays_stable(client):
    payload = {"url": "https://example.com/stable"}
    headers = {"Idempotency-Key": "stable-key"}

    responses = [client.post("/links", json=payload, headers=headers) for _ in range(3)]

    assert responses[0].status_code == 201
    assert responses[1].status_code == 200
    assert responses[2].status_code == 200

    codes = {r.json()["code"] for r in responses}
    created_ats = {r.json()["created_at"] for r in responses}
    assert len(codes) == 1
    assert len(created_ats) == 1


def test_conflicting_retry_same_key_different_url(client):
    headers = {"Idempotency-Key": "conflict-key"}
    first = client.post("/links", json={"url": "https://example.com/one"}, headers=headers)
    second = client.post("/links", json={"url": "https://example.com/two"}, headers=headers)
    assert first.status_code == 201
    assert second.status_code == 409


def test_conflicting_retry_same_url_different_alias(client):
    headers = {"Idempotency-Key": "conflict-key-2"}
    first = client.post(
        "/links",
        json={"url": "https://example.com/same", "custom_alias": "alias-one"},
        headers=headers,
    )
    second = client.post(
        "/links",
        json={"url": "https://example.com/same", "custom_alias": "alias-two"},
        headers=headers,
    )
    assert first.status_code == 201
    assert second.status_code == 409


def test_idempotency_header_is_case_insensitive(client):
    payload = {"url": "https://example.com/case"}
    first = client.post("/links", json=payload, headers={"Idempotency-Key": "case-key"})
    second = client.post("/links", json=payload, headers={"idempotency-key": "case-key"})
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["code"] == second.json()["code"]


def test_no_idempotency_key_never_deduplicates(client):
    payload = {"url": "https://example.com/no-key"}
    first = client.post("/links", json=payload)
    second = client.post("/links", json=payload)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["code"] != second.json()["code"]
