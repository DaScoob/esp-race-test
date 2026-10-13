import pathlib
import re

from fastapi.testclient import TestClient

from conftest import TEST_ADMIN_AUTH, TEST_DEVICE_AUTH, TEST_ADMIN_KEY, TEST_DEVICE_KEY, make_heartbeat

INTERFACE_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "Interface"
SECRET_CHARS = set(TEST_DEVICE_KEY) | set(TEST_ADMIN_KEY)


def static_files() -> list[pathlib.Path]:
    return [path for path in INTERFACE_DIR.rglob("*") if path.is_file()]


def test_ui_index_served_with_expected_content(client: TestClient):
    response = client.get("/ui/")
    assert response.status_code == 200
    assert "esp-race-test" in response.text
    assert "Keine echten Geräte registriert" in response.text


def test_ui_assets_served(client: TestClient):
    for path, minimum, content_type in (
        ("/ui/app.js", 1, "text/javascript"),
        ("/ui/ui-logic.js", 1, "text/javascript"),
        ("/ui/style.css", 1, "text/css"),
    ):
        response = client.get(path)
        assert response.status_code == 200, path
        assert content_type in response.headers["content-type"], path
        assert len(response.text) >= minimum


def test_ui_falls_back_to_index_and_rejects_unknown_files(client: TestClient):
    assert client.get("/ui").status_code in (200, 307)
    assert client.get("/ui/../../Server/.env").status_code in (404, 403, 400, 304)


def test_shipped_interface_files_contain_no_secrets():
    env_values = []
    env_file = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(("DEVICE_API_KEY=", "ADMIN_API_KEY=")):
                env_values.append(line.partition("=")[2].strip())
    assert env_values, "no .env values found to compare against"
    for path in static_files():
        content = path.read_text(encoding="utf-8", errors="replace")
        for value in env_values:
            assert value not in content, f"secret leaked in {path.name}"
        for pattern in (
            r"ADMIN_API_KEY\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
            r"DEVICE_API_KEY\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}",
            r"localStorage\.setItem\((['\"])(?!esp-race-test-color-mode)",
            r"sessionStorage",
            r"(?<![A-Za-z_])X-Device-Key(?![A-Za-z_])",
        ):
            assert not re.search(pattern, content), f"forbidden pattern {pattern[:40]!r} in {path.name}"


def test_interface_uses_relative_api_paths_only():
    pure_modules = {"ui-logic.js"}
    for path in static_files():
        if path.suffix != ".js":
            continue
        content = path.read_text(encoding="utf-8")
        assert not re.search(r"https?://", content), f"absolute URL in {path.name}"
        if path.name in pure_modules:
            continue
        assert "/api/v1/" in content


def test_interface_end_to_end_flow_through_api(client: TestClient):
    assert client.get("/ui/").status_code == 200
    assert client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH).json() == []
    response = client.get("/api/v1/devices", headers=TEST_DEVICE_AUTH)
    assert response.status_code == 401

    device_auth = dict(TEST_DEVICE_AUTH, **{"Content-Type": "application/json"})
    for mac, channel in (("AA:BB:CC:DD:EE:01", 1), ("AA:BB:CC:DD:EE:02", 1)):
        assert client.post("/api/v1/heartbeat", headers=device_auth,
                           json=make_heartbeat(mac, wifi_channel=channel)).status_code == 200
    devices = client.get("/api/v1/devices", headers=TEST_ADMIN_AUTH).json()
    assert len(devices) == 2
    pairing = client.post("/api/v1/pairings", headers=TEST_ADMIN_AUTH,
                          json={"first": "AA:BB:CC:DD:EE:01", "second": "AA:BB:CC:DD:EE:02"})
    assert pairing.status_code == 201
    body = pairing.json()
    assert len(body["commands"]) == 2
    assert len({c["pairing_id"] for c in body["commands"]}) == 1
    listed = client.get("/api/v1/pairings", headers=TEST_ADMIN_AUTH).json()
    assert all(c["state"] == "pending" for c in listed)
    mismatch = client.post("/api/v1/pairings", headers=TEST_ADMIN_AUTH,
                           json={"first": "AA:BB:CC:DD:EE:09", "second": "AA:BB:CC:DD:EE:01"})
    assert mismatch.status_code == 409
    assert mismatch.json()["detail"]["code"] == "device_offline"
