import json
import sqlite3

from .config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    id           TEXT PRIMARY KEY,
    firmware     TEXT NOT NULL DEFAULT '',
    wifi_rssi    INTEGER NOT NULL DEFAULT 0,
    wifi_channel INTEGER,
    uptime_ms    INTEGER,
    peer_mac     TEXT NOT NULL DEFAULT '',
    peer_active  INTEGER NOT NULL DEFAULT 0,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT NOT NULL,
    device_id TEXT NOT NULL,
    type      TEXT NOT NULL,
    details   TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts DESC);

CREATE TABLE IF NOT EXISTS pairings (
    id         TEXT PRIMARY KEY,
    first      TEXT NOT NULL,
    second     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commands (
    id         TEXT PRIMARY KEY,
    pairing_id TEXT REFERENCES pairings (id) ON DELETE SET NULL,
    device_id  TEXT NOT NULL,
    action     TEXT NOT NULL CHECK (action IN ('pair', 'unpair')),
    peer_mac   TEXT NOT NULL DEFAULT '',
    state      TEXT NOT NULL DEFAULT 'pending'
               CHECK (state IN ('pending', 'ack_ok', 'ack_failed')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    ack_detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_commands_device ON commands (device_id, state);
CREATE INDEX IF NOT EXISTS idx_commands_pairing ON commands (pairing_id);
"""


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(settings.db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def init_db() -> None:
    if "/" in settings.db_path:
        from pathlib import Path

        Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)
    connection = connect()
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


def command_to_dict(row: sqlite3.Row) -> dict:
    return {
        "command_id": row["id"],
        "pairing_id": row["pairing_id"],
        "device_id": row["device_id"],
        "action": row["action"],
        "peer_mac": row["peer_mac"],
        "state": row["state"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "ack_detail": row["ack_detail"],
    }


def event_to_dict(row: sqlite3.Row) -> dict:
    details = None
    if row["details"] is not None:
        try:
            details = json.loads(row["details"])
        except (ValueError, TypeError):
            details = None
    return {
        "id": row["id"],
        "ts": row["ts"],
        "device_id": row["device_id"],
        "type": row["type"],
        "details": details,
    }