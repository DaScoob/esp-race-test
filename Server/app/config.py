import os
from dataclasses import dataclass
from pathlib import Path

_FALLBACK_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key:
            os.environ.setdefault(key, value)


_load_dotenv(_FALLBACK_ENV_FILE)


@dataclass(frozen=True)
class Settings:
    device_api_key: str
    admin_api_key: str
    db_path: str
    online_window_seconds: int
    frontend_origin: str
    ui_dir: str
    downloads_dir: str


def load_settings() -> Settings:
    device_key = os.environ.get("DEVICE_API_KEY", "")
    admin_key = os.environ.get("ADMIN_API_KEY", "")
    db_path = os.environ.get("DB_PATH", "data/race.db")
    try:
        online_window = int(os.environ.get("ONLINE_WINDOW_SECONDS", "15"))
    except ValueError as exc:
        raise RuntimeError("ONLINE_WINDOW_SECONDS must be an integer.") from exc
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "").strip().rstrip("/")
    ui_dir = os.environ.get("UI_DIR", "").strip()
    downloads_dir = os.environ.get("DOWNLOADS_DIR", "").strip()

    problems = []
    if len(device_key) < 32:
        problems.append("DEVICE_API_KEY is missing or shorter than 32 characters.")
    if len(admin_key) < 32:
        problems.append("ADMIN_API_KEY is missing or shorter than 32 characters.")
    if device_key and admin_key and device_key == admin_key:
        problems.append("DEVICE_API_KEY and ADMIN_API_KEY must have different values.")
    if online_window < 1:
        problems.append("ONLINE_WINDOW_SECONDS must be at least 1.")
    if problems:
        raise RuntimeError("Invalid configuration: " + " ".join(problems))

    return Settings(
        device_api_key=device_key,
        admin_api_key=admin_key,
        db_path=db_path,
        online_window_seconds=online_window,
        frontend_origin=frontend_origin,
        ui_dir=ui_dir,
        downloads_dir=downloads_dir,
    )


settings = load_settings()