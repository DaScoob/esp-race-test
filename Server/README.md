# ESP Race API — Server and test interface

FastAPI backend of the ESP Race test environment. Receives heartbeats, events and
acknowledgements directly from ESP32 devices, manages pairing/unpairing commands, and
serves the real-data test interface from the same origin.

**Current status:** private local-network development only. The verified LAN address
is `http://192.168.178.60:6017`, with the interface at `/ui/` and the ZIP index at
`/downloads/`. There is **no public HTTPS deployment**. Do not expose this HTTP service
to the public internet. HTTPS, public origin, and any cross-origin proxy/CORS setup
remain open items.

## Run

```bash
docker compose up -d --build
```

Test suite (host-side test tooling only; the server itself is Docker-only):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The suite runs against an isolated temporary SQLite database (never `data/`);
the `docker`-marked integration test spins up a second compose project
(`race-m3-test`) on `127.0.0.1:6117` with its own `data-test/` volume and
tears everything down afterward. Tests must not populate the runtime database.

| Item | Value |
| --- | --- |
| Local API address | `http://192.168.178.60:6017` (private LAN development only) |
| Test interface | `http://192.168.178.60:6017/ui/` |
| Artifact index | `http://192.168.178.60:6017/downloads/` |
| OpenAPI docs | `http://192.168.178.60:6017/docs` |
| Health (no auth) | `GET /api/v1/health` |
| Database | `./data/race.db` (host bind mount, owned by container user uid 1000) |
| Secrets | `./.env` (never committed, never logged) |

`docker compose restart` preserves all data; the database is created **empty** on
first start and contains no seed/demo records.

> The schema is initialized once at container startup. If you remove `data/race.db*`
> on the host, restart the container afterwards — otherwise requests to missing
> tables return 500 until the next startup.

## Environment variables

| Variable | Meaning |
| --- | --- |
| `DEVICE_API_KEY` | Secret for device endpoints, sent by firmware as `X-Device-Key`. Generated locally, never printed. |
| `ADMIN_API_KEY` | Separate secret for admin endpoints, sent as `X-Admin-Key`. Different value from `DEVICE_API_KEY` (enforced at startup). |
| `DB_PATH` | SQLite path. Set to `/app/data/race.db` by compose (host volume `./data`). |
| `ONLINE_WINDOW_SECONDS` | Online window, default `15`. |
| `FRONTEND_ORIGIN` | Empty → CORS disabled (current local same-origin mode). Non-empty → CORS allows exactly this origin plus `X-Admin-Key`, `X-Device-Key`, `Content-Type`. |

## API contract (v1)

Error envelope for all domain errors: `{"detail": {"code": "...", "message": "..."}}`.
Schema-validation failures use `422` with `detail.code = "validation_error"`.
Missing/invalid API keys always yield `401` with code `unauthorized`; 401 is never
returned as an empty device list.

Device IDs are WLAN station MACs. Any common spelling (`AA:BB:CC:DD:EE:01`,
`aa-bb-cc-dd-ee-01`, `aabbccddee01`) is accepted on input and normalized to
**12 uppercase hex digits without separators** (`AABBCCDDEE01`) in storage and all
responses.

All timestamps are **ISO 8601 UTC strings with microseconds and `Z` suffix**,
e.g. `2026-10-13T19:38:23.795721Z`.

### Device endpoints (firmware only, `X-Device-Key`)

| Route | Status | Purpose |
| --- | --- | --- |
| `POST /api/v1/heartbeat` | 200 | Creates or updates the device record; sets `last_seen = now`. A heartbeat is the **only** way a device record appears. |
| `POST /api/v1/events` | 201 | Stores one real device event. |
| `GET /api/v1/commands?device_id=MAC` | 200 | Polls the oldest `pending` command (or `null`). Polling does **not** consume or ack the command. |
| `POST /api/v1/commands/ack` | 200 | Acknowledges one command. |

Heartbeat request body:

```json
{
  "device_id": "AABBCCDDEE01",
  "firmware": "0.1.0",
  "wifi_rssi": -58,
  "wifi_channel": 1,
  "uptime_ms": 30000,
  "peer_mac": "",
  "peer_active": false
}
```

`peer_mac` (default `""`) and `peer_active` (default `false`) are optional; if
`peer_mac` is empty the server forces `peer_active` to `false`. Everything else is
required. Types: `device_id`/`firmware` string, `wifi_rssi` int (dBm), `wifi_channel`
int, `uptime_ms` int ≥ 0, `peer_active` bool.

Event request body: `device_id` (MAC), `type` (string 1–100), `details` (JSON object
or `null`, ≤ 8192 bytes serialized). Command-ack body: `device_id`, `command_id`,
`success` (bool), `detail` (string ≤ 500 or `null`). Full schemas are served live by
the OpenAPI schema at `/openapi.json`.

Device errors: `400 invalid_mac`, `400 payload_too_large`, `401 unauthorized`,
`403 command_not_owned` (ack for a foreign device), `404 command_unknown`.
Repeated acks are idempotent: the first ack decides `ack_ok`/`ack_failed`, later acks
return the unchanged record.

### Admin endpoints (`X-Admin-Key`)

| Route | Status | Purpose |
| --- | --- | --- |
| `GET /api/v1/devices` | 200 | JSON array of devices, newest heartbeat first. |
| `GET /api/v1/events` | 200 | Real device events, newest first. Query: `limit` (1–1000, default 100), optional `device_id`. |
| `GET /api/v1/pairings` | 200 | Real pairing/unpairing commands, newest first. |
| `POST /api/v1/pairings` | 201 | Body `{"first": "MAC1", "second": "MAC2"}`. |
| `POST /api/v1/unpair/{device_id}` | 201 | Single `unpair` command for that device. |

Device record fields (`GET /api/v1/devices`):

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Normalized STA MAC |
| `last_seen`, `first_seen` | string | ISO 8601 UTC, microsecond `Z` format |
| `firmware` | string | Firmware version as reported by the last heartbeat |
| `wifi_rssi` | int | dBm as reported |
| `wifi_channel` | int or null | Last reported channel |
| `uptime_ms` | int or null | Last reported uptime |
| `peer_mac` | string | Peer MAC as reported by the last heartbeat (`""` if none) |
| `peer_active` | bool | `true` only if the device reported recent real ESP-NOW PINGs from its peer. `esp_now_add_peer` alone is **not** sufficient. |
| `online` | bool | **Server-computed**: heartbeat younger than `ONLINE_WINDOW_SECONDS` (15 s). |

Command record fields (`GET/POST /api/v1/pairings`, `POST /api/v1/unpair/{device_id}`,
`GET /api/v1/commands`, `POST /api/v1/commands/ack`):

| Field | Type | Meaning |
| --- | --- | --- |
| `command_id` | string | `{cmd}_{24 hex}` |
| `pairing_id` | string or null | `{pair}_{24 hex}`; `null` for unpair commands |
| `device_id` | string | Commanded device |
| `action` | `"pair"` \| `"unpair"` | |
| `peer_mac` | string | For `pair`: the other device's MAC; for `unpair`: last known peer or `""` |
| `state` | `"pending"` \| `"ack_ok"` \| `"ack_failed"` | |
| `created_at`, `updated_at` | string | ISO 8601 UTC microsecond `Z` format |
| `ack_detail` | string or null | Free-text acknowledgement detail from the device |

Pairing correlation: one request creates **one pairing row and exactly two command
rows**, one per device, each with the other device's MAC as `peer_mac`. The two
commands share the `pairing_id`; `POST /api/v1/pairings` returns
`{pairing_id, first, second, created_at, commands: [cmd, cmd]}`. An unpair command
has `pairing_id: null`.

Pairing precondition checks (immediately before enqueue, inside one transaction):
both devices must exist and be **online**, and both must report the **same
`wifi_channel`** (unknown channel counts as mismatch). Violations → `409` with code
`device_offline` or `wifi_channel_mismatch`; `400 same_device` for identical MACs,
`400 invalid_mac` for malformed MACs. No check → no commands.

Admin errors: `400 invalid_mac|invalid_request|same_device`, `401 unauthorized`,
`404 device_unknown`, `409 device_offline|wifi_channel_mismatch`, `422`.

## Security posture

- `DEVICE_API_KEY` and `ADMIN_API_KEY` are distinct 43+ character secrets generated at
  first setup; comparisons use constant-time comparison.
- Keys are never logged, never echoed in error bodies, and never sent to the browser.
- `.env` is `chmod 600` and excluded from `.gitignore`d output and the Docker image
  (`.dockerignore`).
- MACs and event payloads are not secrets but real keys/passwords are never stored
  anywhere in the database, events, or logs.
- The container runs as a non-root user (uid 1000). Port 6017 is reachable on the
  configured local network for private testing. Keep the host firewall enabled and do
  not forward this development port from the internet. TLS termination belongs in a
  reverse proxy for any public deployment.
- `/ui/` is served same-origin. The browser uses relative `/api/v1/...` paths and
  runtime-entered admin credentials. CORS remains disabled in this configuration.
- `/downloads/` serves only the dedicated read-only artifact directory, including a
  generated ZIP index. It does not expose the host filesystem, secrets, or database.
- The device API key is compiled into each firmware image. Treat the firmware and
  boards as private test credentials, do not share them, and rotate the device key
  after a test session if the images or boards leave the trusted test setup.

## Verified behaviour (real, automated smoke run, no hardware)

The M3 backend report recorded 28/28 passing tests. The M4 server/interface report
recorded 34/34 passing Python tests, including same-origin UI delivery and API flow.
The latest interface logic tests passed 8/8 after the acceptance-check correction in
this repository. The Python suite was not rerun in this packaging environment because
`pytest` is not installed here.

1. Empty database → `GET /devices` returns `[]`, zero devices, no seed/demo data.
2. Heartbeat registration → device auto-created, correct fields, `online: true`.
3. Pairing of two online devices → 201, one pairing, exactly two `pending` commands
   with shared `pairing_id`.
4. Command poll returns the device's pending command; ack → `ack_ok`; duplicate ack
   is idempotent; `ack_failed` path available via `success: false`.
5. Conflicts: different channels → `409 wifi_channel_mismatch`; unknown/offline
   device → `409 device_offline`; same MAC → `400`; malformed MAC → `400`;
   missing fields → `422`; unknown device in unpair → `404`; foreign command ack →
   not reachable cross-device (`403 command_not_owned` implemented).
6. Unpair → 201, single command, `pairing_id: null`, ack → `ack_ok`.
7. 15 s threshold verified in real time (17 s wait): only the stale device flips to
   `online: false`, freshly heartbeatted device stays online.
8. Persistence: after `docker compose restart`, devices (2), events (1) and commands
   (3 incl. states) are byte-identical except the recomputed `online` flag; a
   post-restart heartbeat updates the same device record (`id` unchanged).

Hardware (ESP32) tests: **not performed**. No physical ESP32 was flashed or connected.
Firmware source and manual flash instructions are in `../Firmware/esp-race-test/`;
the PlatformIO toolchain was not available in this environment, so firmware compilation
is still pending.

## Open deployment items (§10 checklist)

1. Public HTTPS origin — **not deployed**. Current `http://192.168.178.60:6017` is
   private LAN development only.
2. `FRONTEND_ORIGIN` — not needed for the current same-origin `/ui/` setup. A future
   separate origin must be specified before enabling CORS.
3. Reverse proxy — not present. A public deployment needs verified TLS termination,
   API path forwarding, header forwarding, and appropriate timeouts.
4. CORS — disabled in local same-origin mode; must be configured to exactly the real
   frontend origin when origins diverge.
5. Response schemas/timestamp format — documented above, served live at
   `/openapi.json`.
6. Persistent DB path — `./data/race.db` on the host volume; restart test passed.
7. Firmware build and hardware verification — firmware source is present, but the
   PlatformIO toolchain and physical ESP32 checks are pending. Public HTTPS requires a
   real deployment origin and trusted CA chain. `setInsecure()` is prohibited.
