import re
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException

MAC_STRIP = re.compile(r"[:\-. ]")
MAC_RE = re.compile(r"^[0-9A-Fa-f]{12}$")
TS_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def api_error(status_code: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers=headers,
    )


def normalize_mac(value: str) -> str:
    cleaned = MAC_STRIP.sub("", value or "")
    if not MAC_RE.fullmatch(cleaned):
        raise api_error(400, "invalid_mac", "Device ID must be a 12-digit hexadecimal WLAN station MAC.")
    return cleaned.upper()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime(TS_FORMAT)


def parse_ts(value: str) -> datetime:
    try:
        return datetime.strptime(value, TS_FORMAT).replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return datetime.min.replace(tzinfo=timezone.utc)


def is_online(last_seen: str, now: datetime, window_seconds: int) -> bool:
    parsed = parse_ts(last_seen)
    if parsed <= datetime.min.replace(tzinfo=timezone.utc):
        return False
    return (now - parsed).total_seconds() <= window_seconds


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(12)}"