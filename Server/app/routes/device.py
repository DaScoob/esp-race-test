import json

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from ..db import command_to_dict, connect
from ..schemas import CommandAckIn, EventIn, HeartbeatIn
from ..security import require_device_key
from ..util import api_error, normalize_mac, utc_now_iso

MAX_DETAILS_BYTES = 8192

router = APIRouter(dependencies=[Depends(require_device_key)])


@router.post("/heartbeat")
def register_heartbeat(payload: HeartbeatIn) -> JSONResponse:
    device_id = normalize_mac(payload.device_id)
    peer_mac = normalize_mac(payload.peer_mac) if payload.peer_mac else ""
    peer_active = payload.peer_active if peer_mac else False
    now = utc_now_iso()
    connection = connect()
    try:
        connection.execute(
            """
            INSERT INTO devices (id, firmware, wifi_rssi, wifi_channel, uptime_ms,
                                 peer_mac, peer_active, first_seen, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
                firmware = excluded.firmware,
                wifi_rssi = excluded.wifi_rssi,
                wifi_channel = excluded.wifi_channel,
                uptime_ms = excluded.uptime_ms,
                peer_mac = excluded.peer_mac,
                peer_active = excluded.peer_active,
                last_seen = excluded.last_seen
            """,
            (device_id, payload.firmware, payload.wifi_rssi, payload.wifi_channel,
             payload.uptime_ms, peer_mac, int(peer_active), now, now),
        )
        connection.commit()
    finally:
        connection.close()
    return JSONResponse(status_code=200, content={"status": "ok", "device_id": device_id})


@router.post("/events")
def store_event(payload: EventIn) -> JSONResponse:
    device_id = normalize_mac(payload.device_id)
    now = utc_now_iso()
    details_json = None
    if payload.details is not None:
        details_json = json.dumps(payload.details, separators=(",", ":"))
        if len(details_json) > MAX_DETAILS_BYTES:
            raise api_error(400, "payload_too_large", "Event details exceed 8192 bytes when serialized.")
    connection = connect()
    try:
        cursor = connection.execute(
            "INSERT INTO events (ts, device_id, type, details) VALUES (?, ?, ?, ?)",
            (now, device_id, payload.type, details_json),
        )
        connection.commit()
        event_id = cursor.lastrowid
    finally:
        connection.close()
    return JSONResponse(status_code=201, content={"id": event_id, "ts": now, "device_id": device_id, "type": payload.type})


@router.get("/commands")
def poll_command(device_id: str = Query(min_length=1)) -> JSONResponse:
    device_id = normalize_mac(device_id)
    connection = connect()
    try:
        row = connection.execute(
            """
            SELECT * FROM commands
            WHERE device_id = ? AND state = 'pending'
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()
    finally:
        connection.close()
    return JSONResponse(status_code=200, content={"command": command_to_dict(row) if row else None})


@router.post("/commands/ack")
def acknowledge_command(payload: CommandAckIn) -> JSONResponse:
    device_id = normalize_mac(payload.device_id)
    now = utc_now_iso()
    connection = connect()
    try:
        row = connection.execute(
            "SELECT * FROM commands WHERE id = ?",
            (payload.command_id,),
        ).fetchone()
        if row is None:
            raise api_error(404, "command_unknown", "The referenced command does not exist.")
        if row["device_id"] != device_id:
            raise api_error(403, "command_not_owned", "The command does not belong to the given device.")
        if row["state"] == "pending":
            new_state = "ack_ok" if payload.success else "ack_failed"
            connection.execute(
                "UPDATE commands SET state = ?, updated_at = ?, ack_detail = ? WHERE id = ?",
                (new_state, now, payload.detail, payload.command_id),
            )
            connection.commit()
        row = connection.execute(
            "SELECT * FROM commands WHERE id = ?",
            (payload.command_id,),
        ).fetchone()
    finally:
        connection.close()
    return JSONResponse(status_code=200, content={"command": command_to_dict(row)})