import time
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import connect
from app.util import TS_FORMAT
from conftest import MAC_A, MAC_A_NORM, MAC_B, MAC_B_NORM, TEST_ADMIN_AUTH, TEST_DEVICE_AUTH, make_heartbeat


def _register(client: TestClient, mac: str) -> None:
    assert client.post("/api/v1/heartbeat", headers=TEST_DEVICE_AUTH, json=make_heartbeat(mac)).status_code == 200


def _set_last_seen(seconds_ago: int) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).strftime(TS_FORMAT)
    connection = connect()
    try:
        connection.execute("UPDATE devices SET last_seen = ?", (stale,))
        connection.commit()
    finally:
        connection.close()


def _online_map(client: TestClient) -> dict:
    devices = client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH).json()
    return {record["id"]: record["online"] for record in devices}


def test_fresh_heartbeat_is_online(client: TestClient):
    _register(client, MAC_A)
    assert _online_map(client) == {MAC_A_NORM: True}


def test_backdated_heartbeat_beyond_15s_is_offline(client: TestClient):
    _register(client, MAC_A)
    _set_last_seen(16)
    assert _online_map(client) == {MAC_A_NORM: False}
    _set_last_seen(14)
    assert _online_map(client) == {MAC_A_NORM: True}


def test_only_stale_device_flips_offline(client: TestClient):
    _register(client, MAC_A)
    _register(client, MAC_B)
    _set_last_seen(16)
    online = _online_map(client)
    assert online[MAC_A_NORM] is False
    assert online[MAC_B_NORM] is False
    _set_last_seen(10)
    online = _online_map(client)
    assert online == {MAC_A_NORM: True, MAC_B_NORM: True}
    connection = connect()
    try:
        stale_value = (datetime.now(timezone.utc) - timedelta(seconds=20)).strftime(TS_FORMAT)
        fresh_value = (datetime.now(timezone.utc) - timedelta(seconds=5)).strftime(TS_FORMAT)
        connection.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (stale_value, MAC_A_NORM))
        connection.execute("UPDATE devices SET last_seen = ? WHERE id = ?", (fresh_value, MAC_B_NORM))
        connection.commit()
    finally:
        connection.close()
    online = _online_map(client)
    assert online == {MAC_A_NORM: False, MAC_B_NORM: True}


def test_real_time_15s_threshold(client: TestClient):
    _register(client, MAC_A)
    _register(client, MAC_B)
    time.sleep(16)
    online = _online_map(client)
    assert online == {MAC_A_NORM: False, MAC_B_NORM: False}
    _register(client, MAC_A)
    online = _online_map(client)
    assert online == {MAC_A_NORM: True, MAC_B_NORM: False}