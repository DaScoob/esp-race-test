# CHANGELOG — esp-race-test

## 2026-10-13 — Complete source package and firmware preparation

- Imported the latest M4 server/interface source and the verified downloads index fix as the base for a complete, self-contained project source package.
- Added ESP32 firmware source for the documented device API contract. It handles actual MAC normalization, nested command responses, command acknowledgements, ESP-NOW peer commands, and real PING-based `peer_active` reporting. Local HTTP is restricted to the configured private LAN origin; HTTPS fails closed unless a trusted CA is configured.
- Added PlatformIO profiles for classic ESP32 Dev Module and ESP32-S3 DevKitC-1, a non-secret configuration template, and manual build/flash/test instructions. No physical device is accessed or flashed.
- Tightened acceptance check 5 so it passes only when the server reports exactly two reciprocal commands with one shared `pairing_id`; added regression cases. The interface now displays the server's `last_seen` timestamp and filters pairing choices to online devices on the selected device's channel.
- Updated server and project documentation for the verified LAN-only deployment and actual open items. Added an OpenCode prompt that limits the other AI to server administration and prohibits application-code changes.
- Verification: interface logic tests **8/8 passed** using `node Interface/tests/ui-logic.test.mjs`. The latest server report recorded **34/34 pytest checks**, but Python tests were not rerun here because `pytest` is not installed. Firmware compilation remains pending because PlatformIO is unavailable; no physical ESP32 hardware tests were performed.

## 2026-10-13 — Fix: /downloads endpoint returned 404 without index (download verification)

- Diagnosis: the exact file URL (`/downloads/esp-race-test-2026-10-13-m4-interface.zip`) returned HTTP 200 with a byte-identical file all along, but the bare `GET /downloads/` endpoint returned 404 (`{"detail":"Not Found"}` — StaticFiles had no directory index), which the earlier test output reported and read as "endpoint not reachable". Host-side tests also looped back internally and never exercised the external port-forward path.
- Fix (smallest change): serve an index page for the dedicated artifact directory only — `StaticFiles(..., html=True)` on `/downloads` plus a generated `artifacts/index.html` (name, size, creation date, SHA-256 prefix for each ZIP), created by new `Server/scripts/artifacts_index.py`. Container recreated; runtime database stayed empty (`[]`) and untouched.
- Verification: `GET /downloads/` → HTTP 200 (index, 1,474 bytes); file URL → HTTP 200, valid ZIP (`testzip()` clean), 43,486 bytes, SHA-256 `7c59c362d281d876…` identical to source; both tested from the host LAN IP **and** from a separate container network namespace through the host's DNAT port-forwarding path. Host firewall `ufw` is active; published-port reachability for LAN clients was already confirmed via the base URL. Remaining unverified: download from a physical second LAN device (none available in this environment).

## 2026-10-13 — M4: test interface at /ui + per-task artifact ZIPs

- New static test interface (`BierPeter/Interface/`: `index.html`, `style.css`, `app.js`, `ui-logic.js`), served same-origin at `/ui/`:
  - Admin key entered at runtime in a native `<dialog>`, kept only in memory, sent as `X-Admin-Key`. No keys in shipped JS, browser storage (except color-mode UI preference), or URLs.
  - Polls devices, events, and pairings every 5 s; empty devices show “Keine echten Geräte registriert”.
  - API outages show “Server nicht erreichbar” and keep the last successfully received data explicitly labeled stale; server-reported `online`/`wifi_channel` are used exclusively.
  - Pairing offered only for two online devices with equal channel; after a successful request the commands render “Befehl wartet (pending)”; acknowledgements only from real `ack_ok`/`ack_failed` states.
  - “ESP-NOW-Verbindung bestätigt” only when both devices are online, both report `peer_active=true`, and `peer_mac` values are reciprocal (pure function `findConnectionConfirmed`).
  - Event log populated exclusively from `GET /api/v1/events`.
  - All eight acceptance checks displayed with status + evidence from real API results; monotonic latching; no check passes from clicks alone. Distinct handling of 401, 409 (`device_offline` / `wifi_channel_mismatch` mapped), 403/404, network errors, and invalid server responses.
- Server: added `UI_DIR` and `DOWNLOADS_DIR` mount support (`app/main.py`, `app/config.py`); compose mounts `../Interface:/app/ui:ro` and `../artifacts:/app/downloads:ro`; port binding moved from `127.0.0.1:6017` to `6017` (LAN reachability for the artifact downloads path, `192.168.178.60`).
- Tests: new `Server/tests/test_ui.py` (same-origin serving, content assertions, secret-leak checks on shipped files, relative-path rule, end-to-end API flow); pure-logic tests `Interface/tests/ui-logic.test.mjs` via `node --test` (8/8). Suite now 34 passed / 0 failed. `test_ui.py` standalone-run robustness fix in conftest (`init_db()` in cleanup fixture).
- Runtime database untouched and empty after rollout (verified `[]`); per-task ZIP snapshot process established (`SERVER_INFO.md`, `CHANGELOG.md`, `ISSUES.md` included in every ZIP).

## 2026-10-13 — M3: automated pytest suite

- Added `Server/tests/` (auth, schemas, pairing/commands, 15 s offline threshold incl. real-time run, docker restart persistence), `pytest.ini`, test-only venv (`Server/.venv`, gitignored).
- Result: 28 passed / 0 failed. Test fixes during development (409-coverage test, oldest-first test, deterministic event ordering assertion); docker test fixture now pre-creates the bind-mount dir to avoid a root-owned volume. No server-code changes.
- Ops note documented: removing `data/race.db*` requires a container restart (schema init happens at startup); runtime DB reset to empty as required.

## 2026-10-13 — M2/M1: FastAPI backend + Docker

- Full §5 API contract (device + admin endpoints, X-Device-Key/X-Admin-Key), SQLite WAL storage (`Server/data/race.db`), pairing = 2 commands with shared `pairing_id`, distinguishable 409s, 15 s online window, non-root container, healthcheck, compose port 6017, generated distinct strong secrets in `Server/.env` (0600, gitignored, never printed).
- Verified: 24/24 curl smoke checks incl. 15 s threshold (real time) and restart persistence.
