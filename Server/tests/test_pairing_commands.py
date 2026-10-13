from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import connect
from app.util import TS_FORMAT
from conftest import (
    MAC_A,
    MAC_A_NORM,
    MAC_B,
    MAC_B_NORM,
    MAC_X_NORM,
    TEST_ADMIN_AUTH,
    TEST_DEVICE_AUTH,
    make_heartbeat,
)


def register(client: TestClient, mac: str, channel: int = 1) -> None:
    response = client.post("/api/v1/heartbeat", headers=TEST_DEVICE_AUTH, json=make_heartbeat(mac, wifi_channel=channel))
    assert response.status_code == 200


def request_pairing(client: TestClient, first: str, second: str):
    return client.post(
        "/api/v1/pairings",
        headers=TEST_ADMIN_AUTH,
        json={"first": first, "second": second},
    )


def poll(client: TestClient, mac: str):
    return client.get("/api/v1/commands", params={"device_id": mac}, headers=TEST_DEVICE_AUTH).json()["command"]


def ack(client: TestClient, mac: str, command_id: str, success: bool, detail: str | None = None):
    return client.post(
        "/api/v1/commands/ack",
        headers=TEST_DEVICE_AUTH,
        json={"device_id": mac, "command_id": command_id, "success": success, "detail": detail},
    )


def test_pairing_creates_exactly_two_commands_with_shared_pairing_id(client: TestClient):
    register(client, MAC_A)
    register(client, MAC_B)
    response = request_pairing(client, MAC_A, MAC_B)
    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"pairing_id", "first", "second", "created_at", "commands"}
    assert body["pairing_id"].startswith("pair_")
    assert set(first["device_id"] for first in body["commands"]) == {MAC_A_NORM, MAC_B_NORM}
    assert len(set(command["command_id"] for command in body["commands"])) == 2
    command_a, command_b = body["commands"]
    assert command_a["device_id"] == MAC_A_NORM and command_a["peer_mac"] == MAC_B_NORM
    assert command_b["device_id"] == MAC_B_NORM and command_b["peer_mac"] == MAC_A_NORM
    for command in body["commands"]:
        assert command["pairing_id"] == body["pairing_id"]
        assert command["action"] == "pair"
        assert command["state"] == "pending"
        assert command["ack_detail"] is None

    listed = client.get("/api/v1/pairings", headers=TEST_ADMIN_AUTH).json()
    assert len(listed) == 2
    assert all(command["pairing_id"] == body["pairing_id"] for command in listed)
    assert set(command["state"] for command in listed) == {"pending"}


def test_pairing_conflicts_are_distinguishable_409s(client: TestClient):
    register(client, MAC_A, channel=1)
    register(client, MAC_B, channel=11)

    response = request_pairing(client, MAC_A, MAC_B)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "wifi_channel_mismatch"

    response = request_pairing(client, MAC_A, MAC_X_NORM)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "device_offline"

    listed = client.get("/api/v1/pairings", headers=TEST_ADMIN_AUTH).json()
    assert listed == []


def _backdate_all_devices(seconds: int) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(seconds=seconds)).strftime(TS_FORMAT)
    connection = connect()
    try:
        connection.execute("UPDATE devices SET last_seen = ?", (stale,))
        connection.commit()
    finally:
        connection.close()


def test_pairing_rejects_offline_registered_device(client: TestClient):
    register(client, MAC_A)
    _backdate_all_devices(25)

    response = request_pairing(client, MAC_A, MAC_B)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "device_offline"


def test_pairing_validation_errors(client: TestClient):
    register(client, MAC_A)
    response = request_pairing(client, MAC_A, MAC_A)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "same_device"

    response = request_pairing(client, MAC_A, "not-a-mac")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_mac"

    response = client.post("/api/v1/pairings", headers=TEST_ADMIN_AUTH, json={"second": MAC_B_NORM})
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_request"

    response = client.post("/api/v1/pairings", headers={"X-Admin-Key": "nope-nope-nope-nope-nope"}, json={"first": MAC_A, "second": MAC_B_NORM})
    assert response.status_code == 401


def test_command_poll_and_ack_states(client: TestClient):
    register(client, MAC_A)
    register(client, MAC_B)
    body = request_pairing(client, MAC_A, MAC_B).json()
    cmd_a = body["commands"][0]["command_id"]
    cmd_b = body["commands"][1]["command_id"]

    polled_a = poll(client, MAC_A)
    assert polled_a["command_id"] == cmd_a
    assert polled_a["state"] == "pending"
    assert poll(client, MAC_A)["command_id"] == cmd_a

    response = ack(client, MAC_A, cmd_a, success=True, detail="esp_now_add_peer ok")
    assert response.status_code == 200
    assert response.json()["command"]["state"] == "ack_ok"
    assert response.json()["command"]["ack_detail"] == "esp_now_add_peer ok"

    response = ack(client, MAC_B, cmd_b, success=False, detail="peer not found")
    assert response.json()["command"]["state"] == "ack_failed"

    listed = client.get("/api/v1/pairings", headers=TEST_ADMIN_AUTH).json()
    states = {command["command_id"]: command["state"] for command in listed}
    assert states[cmd_a] == "ack_ok"
    assert states[cmd_b] == "ack_failed"

    assert poll(client, MAC_A) is None


def test_repeated_ack_is_idempotent(client: TestClient):
    register(client, MAC_A)
    register(client, MAC_B)
    cmd_a = request_pairing(client, MAC_A, MAC_B).json()["commands"][0]["command_id"]

    assert ack(client, MAC_A, cmd_a, success=True).json()["command"]["state"] == "ack_ok"
    repeat = ack(client, MAC_A, cmd_a, success=False, detail="late retry says failure")
    assert repeat.status_code == 200
    assert repeat.json()["command"]["state"] == "ack_ok"


def test_cross_device_ack_rejected(client: TestClient):
    register(client, MAC_A)
    register(client, MAC_B)
    commands = request_pairing(client, MAC_A, MAC_B).json()["commands"]
    cmd_a = commands[0]["command_id"]
    cmd_b = commands[1]["command_id"]

    response = ack(client, MAC_A, cmd_b, success=True)
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "command_not_owned"

    response = ack(client, MAC_A, "cmd_doesnotexist000000", success=True)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "command_unknown"


def test_multiple_pending_commands_served_oldest_first(client: TestClient):
    register(client, MAC_A)
    register(client, MAC_B)
    first_pairing = request_pairing(client, MAC_A, MAC_B).json()
    second_pairing = request_pairing(client, MAC_A, MAC_B).json()

    first_command = poll(client, MAC_A)
    assert first_command["pairing_id"] == first_pairing["pairing_id"]
    ack(client, MAC_A, first_command["command_id"], success=True)

    second_command = poll(client, MAC_A)
    assert second_command["pairing_id"] == second_pairing["pairing_id"]
    ack(client, MAC_A, second_command["command_id"], success=True)

    unpair_cmd = client.post(f"/api/v1/unpair/{MAC_A_NORM}", headers=TEST_ADMIN_AUTH).json()["command"]
    third = poll(client, MAC_A)
    assert third["command_id"] == unpair_cmd["command_id"]


def test_unpair_command_creation_and_ack(client: TestClient):
    register(client, MAC_A)
    response = client.post(f"/api/v1/unpair/{MAC_A_NORM}", headers=TEST_ADMIN_AUTH)
    assert response.status_code == 201
    command = response.json()["command"]
    assert set(command.keys()) == {
        "command_id", "pairing_id", "device_id", "action", "peer_mac",
        "state", "created_at", "updated_at", "ack_detail",
    }
    assert command["pairing_id"] is None
    assert command["action"] == "unpair"
    assert command["device_id"] == MAC_A_NORM
    assert command["state"] == "pending"
    assert command["peer_mac"] == ""

    acked = ack(client, MAC_A, command["command_id"], success=True, detail="peer removed")
    assert acked.status_code == 200
    assert acked.json()["command"]["state"] == "ack_ok"


def test_unpair_unknown_device_404(client: TestClient):
    response = client.post(f"/api/v1/unpair/{MAC_X_NORM}", headers=TEST_ADMIN_AUTH)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "device_unknown"


def test_commands_endpoints_require_device_key(client: TestClient):
    register(client, MAC_A)
    register(client, MAC_B)
    assert client.post(
        "/api/v1/pairings", json={"first": MAC_A, "second": MAC_B}
    ).status_code == 401
    assert client.get(
        "/api/v1/commands", params={"device_id": MAC_A}
    ).status_code == 401
    assert client.post(
        "/api/v1/commands/ack",
        json={"device_id": MAC_A_NORM, "command_id": "cmd_x", "success": True},
    ).status_code == 401