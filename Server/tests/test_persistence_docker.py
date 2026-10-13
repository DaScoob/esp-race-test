import json
import pathlib
import shutil
import subprocess
import time
import urllib.request

import pytest

from conftest import MAC_A, MAC_B, make_heartbeat

SERVER_DIR = pathlib.Path(__file__).resolve().parent.parent
TEST_PORT = 6117
STACK = f"http://127.0.0.1:{TEST_PORT}"


def _compose(*args: str) -> None:
    result = subprocess.run(
        ["docker", "compose", "-p", "race-m3-test", "-f", "docker-compose.yml",
         "-f", "tests/docker-compose.test.yml", *args],
        cwd=SERVER_DIR,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, f"docker compose {' '.join(args)} failed: {result.stderr}"


def _wait_healthy(deadline_s: int = 40) -> None:
    url = f"{STACK}/api/v1/health"
    end = time.monotonic() + deadline_s
    last_error: Exception | None = None
    while time.monotonic() < end:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    raise AssertionError(f"isolated test stack never became healthy: {last_error}")


def _request(path: str, headers: dict, body: dict | None = None, method: str = "GET") -> tuple[int, dict | list]:
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{STACK}{path}", headers=headers, data=data, method=method)
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode())


def _read_env(name: str) -> str:
    for line in (SERVER_DIR / ".env").read_text().splitlines():
        if line.startswith(f"{name}="):
            return line.partition("=")[2].strip()
    raise AssertionError(f"{name} missing from .env")


@pytest.fixture(scope="module")
def isolated_stack():
    (SERVER_DIR / "data-test").mkdir(parents=True, exist_ok=True)
    _compose("up", "-d", "--quiet-pull")
    try:
        _wait_healthy()
        yield
    finally:
        _compose("down", "--remove-orphans")
        shutil.rmtree(SERVER_DIR / "data-test", ignore_errors=True)


@pytest.mark.docker
def test_persistence_across_real_container_restart(isolated_stack):
    device_auth = {"X-Device-Key": _read_env("DEVICE_API_KEY"), "Content-Type": "application/json"}
    admin_auth = {"X-Admin-Key": _read_env("ADMIN_API_KEY"), "Content-Type": "application/json"}

    status, devices = _request("/api/v1/devices", admin_auth)
    assert status == 200 and devices == []

    for mac in (MAC_A, MAC_B):
        status, _ = _request("/api/v1/heartbeat", device_auth, make_heartbeat(mac, wifi_channel=1), method="POST")
        assert status == 200

    status, created = _request(
        "/api/v1/pairings", admin_auth, {"first": MAC_A, "second": MAC_B}, method="POST")
    assert status == 201
    assert created["pairing_id"]
    assert len(created["commands"]) == 2

    _compose("restart")
    _wait_healthy()

    status, devices = _request("/api/v1/devices", admin_auth)
    assert status == 200
    assert len(devices) == 2
    assert {record["id"] for record in devices} == {"AABBCCDDEE01", "AABBCCDDEE02"}
    assert all(record["online"] is True for record in devices)

    status, pairings = _request("/api/v1/pairings", admin_auth)
    assert status == 200
    assert len(pairings) == 2
    assert all(command["pairing_id"] == created["pairing_id"] for command in pairings)
    assert all(command["state"] == "pending" for command in pairings)