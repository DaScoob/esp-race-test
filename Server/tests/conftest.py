import atexit
import os
import pathlib
import shutil
import tempfile

import pytest

_TEST_DIR = tempfile.mkdtemp(prefix="race-api-tests-")

os.environ["DB_PATH"] = os.path.join(_TEST_DIR, "race-test.db")
os.environ["ONLINE_WINDOW_SECONDS"] = "15"
os.environ["FRONTEND_ORIGIN"] = ""
os.environ["UI_DIR"] = str(pathlib.Path(__file__).resolve().parent.parent.parent / "Interface")

TEST_DEVICE_KEY = "test-device-key-1234567890abcdef1234567890"
TEST_ADMIN_KEY = "test-admin-key-fedcba0987654321fedcba098765"
os.environ["DEVICE_API_KEY"] = TEST_DEVICE_KEY
os.environ["ADMIN_API_KEY"] = TEST_ADMIN_KEY

atexit.register(lambda: shutil.rmtree(_TEST_DIR, ignore_errors=True))

from fastapi.testclient import TestClient

from app.main import app
from app.util import TS_FORMAT

TEST_DEVICE_AUTH = {"X-Device-Key": TEST_DEVICE_KEY}
TEST_ADMIN_AUTH = {"X-Admin-Key": TEST_ADMIN_KEY}

MAC_A = "AA:BB:CC:DD:EE:01"
MAC_B = "AA:BB:CC:DD:EE:02"
MAC_A_NORM = "AABBCCDDEE01"
MAC_B_NORM = "AABBCCDDEE02"
MAC_X_NORM = "AABBCCDDEE99"


def make_heartbeat(device_id: str, **overrides) -> dict:
    payload = {
        "device_id": device_id,
        "firmware": "0.1.0",
        "wifi_rssi": -58,
        "wifi_channel": 1,
        "uptime_ms": 1000,
        "peer_mac": "",
        "peer_active": False,
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def clean_database():
    yield
    from app.db import connect, init_db

    init_db()
    connection = connect()
    try:
        connection.execute("DELETE FROM commands")
        connection.execute("DELETE FROM pairings")
        connection.execute("DELETE FROM events")
        connection.execute("DELETE FROM devices")
        connection.execute("DELETE FROM sqlite_sequence")
        connection.commit()
    finally:
        connection.close()