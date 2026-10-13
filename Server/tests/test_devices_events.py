import re

from fastapi.testclient import TestClient

from conftest import MAC_A, MAC_A_NORM, MAC_B, MAC_B_NORM, TEST_ADMIN_AUTH, TEST_DEVICE_AUTH, make_heartbeat

TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


def test_empty_database_returns_empty_device_array_with_no_seed_data(client: TestClient):
    response = client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH)
    assert response.status_code == 200
    assert response.json() == []
    events = client.get("/api/v1/events", headers=TEST_ADMIN_AUTH).json()
    assert events == []
    pairings = client.get("/api/v1/pairings", headers=TEST_ADMIN_AUTH).json()
    assert pairings == []


def test_heartbeat_registers_device_with_complete_schema(client: TestClient):
    response = client.post("/api/v1/heartbeat", headers=TEST_DEVICE_AUTH, json=make_heartbeat(MAC_A))
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "device_id": MAC_A_NORM}

    devices = client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH).json()
    assert len(devices) == 1
    record = devices[0]
    assert set(record.keys()) == {
        "id", "last_seen", "first_seen", "firmware", "wifi_rssi",
        "wifi_channel", "uptime_ms", "peer_mac", "peer_active", "online",
    }
    assert record["id"] == MAC_A_NORM
    assert record["firmware"] == "0.1.0"
    assert isinstance(record["wifi_rssi"], int)
    assert isinstance(record["wifi_channel"], int)
    assert isinstance(record["uptime_ms"], int)
    assert record["peer_mac"] == ""
    assert record["peer_active"] is False
    assert record["online"] is True
    assert TS_RE.fullmatch(record["last_seen"])
    assert TS_RE.fullmatch(record["first_seen"])


def test_mac_spellings_normalize_to_single_record(client: TestClient):
    client.post("/api/v1/heartbeat", headers=TEST_DEVICE_AUTH, json=make_heartbeat("aa:bb:cc:dd:ee:03"))
    devices = client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH).json()
    assert len(devices) == 1
    assert devices[0]["id"] == "AABBCCDDEE03"
    client.post("/api/v1/heartbeat", headers=TEST_DEVICE_AUTH, json=make_heartbeat("aabbccddee03"))
    devices = client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH).json()
    assert len(devices) == 1
    client.post("/api/v1/heartbeat", headers=TEST_DEVICE_AUTH, json=make_heartbeat("aa-bb-cc-dd-ee-0f"))
    devices = client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH).json()
    assert {record["id"] for record in devices} == {"AABBCCDDEE03", "AABBCCDDEE0F"}


def test_heartbeat_update_overwrites_state_not_identity(client: TestClient):
    client.post("/api/v1/heartbeat", headers=TEST_DEVICE_AUTH, json=make_heartbeat(MAC_A, firmware="0.1.0", uptime_ms=1000))
    client.post(
        "/api/v1/heartbeat",
        headers=TEST_DEVICE_AUTH,
        json=make_heartbeat(MAC_A, firmware="0.2.0", wifi_channel=6, uptime_ms=2000, peer_mac=MAC_B_NORM, peer_active=True),
    )
    devices = client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH).json()
    assert len(devices) == 1
    record = devices[0]
    assert record["id"] == MAC_A_NORM
    assert record["firmware"] == "0.2.0"
    assert record["wifi_channel"] == 6
    assert record["uptime_ms"] == 2000
    assert record["peer_mac"] == MAC_B_NORM
    assert record["peer_active"] is True
    assert record["last_seen"] >= record["first_seen"]


def test_peer_active_forced_false_without_peer_mac(client: TestClient):
    client.post(
        "/api/v1/heartbeat",
        headers=TEST_DEVICE_AUTH,
        json=make_heartbeat(MAC_A, peer_mac="", peer_active=True),
    )
    record = client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH).json()[0]
    assert record["peer_mac"] == ""
    assert record["peer_active"] is False


def test_device_record_survives_schema_reinit_without_seed_replacement(client: TestClient):
    client.post("/api/v1/heartbeat", headers=TEST_DEVICE_AUTH, json=make_heartbeat(MAC_A))
    client.post(
        "/api/v1/events",
        headers=TEST_DEVICE_AUTH,
        json={"device_id": MAC_A, "type": "esp_now_ping", "details": {"ok": True}},
    )
    from app.db import connect, init_db

    init_db()
    connection = connect()
    try:
        n_devices = connection.execute("SELECT COUNT(*) AS n FROM devices").fetchone()["n"]
        n_events = connection.execute("SELECT COUNT(*) AS n FROM events").fetchone()["n"]
    finally:
        connection.close()
    assert (n_devices, n_events) == (1, 1)


def test_event_schema_and_ordering(client: TestClient):
    for i in range(3):
        response = client.post(
            "/api/v1/events",
            headers=TEST_DEVICE_AUTH,
            json={"device_id": MAC_B, "type": "esp_now_ping", "details": {"seq": i}},
        )
        assert response.status_code == 201
        created = response.json()
        assert created["device_id"] == MAC_B_NORM
        assert created["type"] == "esp_now_ping"
        assert TS_RE.fullmatch(created["ts"])

    response = client.post(
        "/api/v1/events",
        headers=TEST_DEVICE_AUTH,
        json={"device_id": MAC_B, "type": "boot"},
    )
    assert response.status_code == 201

    events = client.get("/api/v1/events", headers=TEST_ADMIN_AUTH).json()
    assert len(events) == 4
    assert all(TS_RE.fullmatch(event["ts"]) for event in events)
    expected = sorted(
        events, key=lambda event: (event["ts"], event["id"]), reverse=True
    )
    assert events == expected
    boot = next(event for event in events if event["type"] == "boot")
    assert boot["details"] is None
    ping_events = [event for event in events if event["type"] == "esp_now_ping"]
    assert [event["details"]["seq"] for event in ping_events] == [2, 1, 0]
    for event in events:
        assert set(event.keys()) == {"id", "ts", "device_id", "type", "details"}
        assert isinstance(event["id"], int)
        assert isinstance(event["device_id"], str)

    filtered = client.get(
        "/api/v1/events", headers=TEST_ADMIN_AUTH, params={"device_id": MAC_B_NORM}
    ).json()
    assert len(filtered) == 4
    filtered = client.get(
        "/api/v1/events", headers={"X-Admin-Key": "wrong"}, params={"device_id": MAC_B_NORM}
    ).status_code == 401
    assert filtered

    oversized = client.post(
        "/api/v1/events",
        headers=TEST_DEVICE_AUTH,
        json={"device_id": MAC_B, "type": "big", "details": {"blob": "x" * 9000}},
    )
    assert oversized.status_code == 400
    assert oversized.json()["detail"]["code"] == "payload_too_large"