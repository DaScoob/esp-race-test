from typing import Any

from pydantic import BaseModel, Field


class HeartbeatIn(BaseModel):
    device_id: str
    firmware: str = Field(max_length=100)
    wifi_rssi: int
    wifi_channel: int
    uptime_ms: int = Field(ge=0)
    peer_mac: str = Field(default="", max_length=20)
    peer_active: bool = False


class EventIn(BaseModel):
    device_id: str
    type: str = Field(min_length=1, max_length=100)
    details: dict[str, Any] | None = None


class CommandAckIn(BaseModel):
    device_id: str
    command_id: str = Field(min_length=1, max_length=64)
    success: bool
    detail: str | None = Field(default=None, max_length=500)


class PairingRequestIn(BaseModel):
    first: str
    second: str