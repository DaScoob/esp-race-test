from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from ..config import settings
from ..db import command_to_dict, connect, event_to_dict
from ..security import require_admin_key
from ..util import api_error, is_online, new_id, normalize_mac, parse_ts, utc_now_iso

router = APIRouter(dependencies=[Depends(require_admin_key)])


def _device_dict(row, now) -> dict:
    return {
        "id": row["id"],
        "last_seen": row["last_seen"],
        "first_seen": row["first_seen"],
        "firmware": row["firmware"],
        "wifi_rssi": row["wifi_rssi"],
        "wifi_channel": row["wifi_channel"],
        "uptime_ms": row["uptime_ms"],
        "peer_mac": row["peer_mac"],
        "peer_active": bool(row["peer_active"]),
        "online": is_online(row["last_seen"], now, settings.online_window_seconds),
    }


@router.get("/devices")
def list_devices() -> JSONResponse:
    now = utc_now_iso()
    now_dt = parse_ts(now)
    connection = connect()
    try:
        rows = connection.execute("SELECT * FROM devices ORDER BY last_seen DESC").fetchall()
    finally:
        connection.close()
    return JSONResponse(status_code=200, content=[_device_dict(row, now_dt) for row in rows])


@router.get("/events")
def list_events(
    limit: int = Query(default=100, ge=1, le=1000),
    device_id: str | None = Query(default=None),
) -> JSONResponse:
    device_id = normalize_mac(device_id) if device_id else None
    connection = connect()
    try:
        if device_id:
            rows = connection.execute(
                "SELECT * FROM events WHERE device_id = ? ORDER BY ts DESC, id DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM events ORDER BY ts DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        connection.close()
    return JSONResponse(status_code=200, content=[event_to_dict(row) for row in rows])


@router.get("/pairings")
def list_pairings() -> JSONResponse:
    connection = connect()
    try:
        rows = connection.execute(
            """
            SELECT c.*, p.first AS pairing_first, p.second AS pairing_second
            FROM commands c
            LEFT JOIN pairings p ON p.id = c.pairing_id
            ORDER BY c.created_at DESC, c.id DESC
            """
        ).fetchall()
    finally:
        connection.close()
    return JSONResponse(status_code=200, content=[command_to_dict(row) for row in rows])


@router.post("/pairings")
def request_pairing(payload: dict) -> JSONResponse:
    raw_first = payload.get("first")
    raw_second = payload.get("second")
    if not isinstance(raw_first, str) or not isinstance(raw_second, str):
        raise api_error(400, "invalid_request", "Body must be a JSON object with string fields 'first' and 'second'.")
    first = normalize_mac(raw_first)
    second = normalize_mac(raw_second)
    if first == second:
        raise api_error(400, "same_device", "Both MAC addresses refer to the same device.")

    now = utc_now_iso()
    connection = connect()
    try:
        connection.execute("BEGIN IMMEDIATE")
        rows = {}
        for device_id in (first, second):
            row = connection.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
            if row is None or not is_online(row["last_seen"], parse_ts(now), settings.online_window_seconds):
                raise api_error(409, "device_offline", f"Device {device_id} is unknown or has no heartbeat within the last {settings.online_window_seconds} seconds.")
            rows[device_id] = row
        channel_first = rows[first]["wifi_channel"]
        channel_second = rows[second]["wifi_channel"]
        if channel_first is None or channel_second is None or channel_first != channel_second:
            raise api_error(409, "wifi_channel_mismatch", f"Devices {first} (channel {channel_first}) and {second} (channel {channel_second}) are not on the same Wi-Fi channel.")

        pairing_id = new_id("pair")
        connection.execute(
            "INSERT INTO pairings (id, first, second, created_at) VALUES (?, ?, ?, ?)",
            (pairing_id, first, second, now),
        )
        commands = []
        for device_id, peer in ((first, second), (second, first)):
            command_id = new_id("cmd")
            connection.execute(
                """
                INSERT INTO commands (id, pairing_id, device_id, action, peer_mac, state, created_at, updated_at)
                VALUES (?, ?, ?, 'pair', ?, 'pending', ?, ?)
                """,
                (command_id, pairing_id, device_id, peer, now, now),
            )
            commands.append({
                "command_id": command_id,
                "pairing_id": pairing_id,
                "device_id": device_id,
                "action": "pair",
                "peer_mac": peer,
                "state": "pending",
                "created_at": now,
                "updated_at": now,
                "ack_detail": None,
            })
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return JSONResponse(status_code=201, content={"pairing_id": pairing_id, "first": first, "second": second, "created_at": now, "commands": commands})


@router.post("/unpair/{device_id}")
def request_unpair(device_id: str) -> JSONResponse:
    device_id = normalize_mac(device_id)
    now = utc_now_iso()
    connection = connect()
    try:
        row = connection.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        if row is None:
            raise api_error(404, "device_unknown", f"Device {device_id} has never sent a heartbeat.")
        command_id = new_id("cmd")
        connection.execute(
            """
            INSERT INTO commands (id, pairing_id, device_id, action, peer_mac, state, created_at, updated_at)
            VALUES (?, NULL, ?, 'unpair', ?, 'pending', ?, ?)
            """,
            (command_id, device_id, row["peer_mac"] or "", now, now),
        )
        connection.commit()
        command_row = connection.execute("SELECT * FROM commands WHERE id = ?", (command_id,)).fetchone()
    finally:
        connection.close()
    return JSONResponse(status_code=201, content={"command": command_to_dict(command_row)})