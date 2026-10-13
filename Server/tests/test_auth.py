from fastapi.testclient import TestClient

from conftest import MAC_A, TEST_ADMIN_KEY, TEST_DEVICE_AUTH


def test_health_is_public(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_devices_without_key_401(client: TestClient):
    response = client.get("/api/v1/devices")
    assert response.status_code == 401
    body = response.json()
    assert body["detail"]["code"] == "unauthorized"
    assert "devices" not in body


def test_devices_with_wrong_key_401(client: TestClient):
    response = client.get("/api/v1/devices", headers={"X-Admin-Key": "not-the-real-key-not-the-real-key!"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthorized"


def test_devices_reject_device_key(client: TestClient):
    response = client.get("/api/v1/devices", headers=TEST_DEVICE_AUTH)
    assert response.status_code == 401


def test_heartbeat_requires_device_key(client: TestClient):
    response = client.post(
        "/api/v1/heartbeat",
        json={"device_id": MAC_A, "firmware": "0.1.0", "wifi_rssi": -58, "wifi_channel": 1, "uptime_ms": 1000},
    )
    assert response.status_code == 401

    response = client.post(
        "/api/v1/heartbeat",
        headers={"X-Device-Key": TEST_ADMIN_KEY},
        json={"device_id": MAC_A, "firmware": "0.1.0", "wifi_rssi": -58, "wifi_channel": 1, "uptime_ms": 1000},
    )
    assert response.status_code == 401

    response = client.get("/api/v1/commands", params={"device_id": MAC_A}, headers={"X-Admin-Key": TEST_ADMIN_KEY})
    assert response.status_code == 401