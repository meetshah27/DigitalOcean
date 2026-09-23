from concurrent.futures import ThreadPoolExecutor


def test_parallel_identical_alias_writes_only_one_succeeds(client):
    def create():
        return client.post(
            "/links", json={"url": "https://example.com/race", "custom_alias": "race-alias"}
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda _: create(), range(10)))

    statuses = sorted(r.status_code for r in responses)
    assert statuses.count(201) == 1
    assert statuses.count(409) == 9


def test_parallel_distinct_alias_writes_all_succeed(client):
    def create(i):
        return client.post(
            "/links",
            json={"url": f"https://example.com/distinct-{i}", "custom_alias": f"distinct-{i}"},
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(create, range(10)))

    assert all(r.status_code == 201 for r in responses)
    codes = {r.json()["code"] for r in responses}
    assert len(codes) == 10


def test_parallel_identical_idempotency_key_only_one_new(client):
    payload = {"url": "https://example.com/idem-race"}
    headers = {"Idempotency-Key": "idem-race-key"}

    def create():
        return client.post("/links", json=payload, headers=headers)

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda _: create(), range(10)))

    statuses = sorted(r.status_code for r in responses)
    assert statuses.count(201) == 1
    assert statuses.count(200) == 9
    codes = {r.json()["code"] for r in responses}
    assert len(codes) == 1


def test_parallel_auto_generated_codes_never_collide(client):
    def create(i):
        return client.post("/links", json={"url": f"https://example.com/auto-{i}"})

    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(create, range(20)))

    assert all(r.status_code == 201 for r in responses)
    codes = {r.json()["code"] for r in responses}
    assert len(codes) == 20
