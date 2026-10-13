from hmac import compare_digest

from fastapi import Header

from .config import settings
from .util import api_error


def _check_key(value: str | None, expected: str) -> None:
    if not value or not compare_digest(value, expected):
        raise api_error(
            401,
            "unauthorized",
            "Missing or invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


async def require_device_key(x_device_key: str | None = Header(default=None, alias="X-Device-Key")) -> None:
    _check_key(x_device_key, settings.device_api_key)


async def require_admin_key(x_admin_key: str | None = Header(default=None, alias="X-Admin-Key")) -> None:
    _check_key(x_admin_key, settings.admin_api_key)