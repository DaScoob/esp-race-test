# esp-race-test

Private test environment for real ESP32 heartbeat, command, and ESP-NOW pairing tests.

The repository contains the complete source for the FastAPI server, its browser interface, and the ESP32 firmware. The interface and API are served by the same local server at `/ui/` and `/api/v1/`. There are no demo devices, seed records, simulated heartbeats, simulated acknowledgements, or browser-stored device data.

## Current verified setup

- Local server origin: `http://192.168.178.60:6017`
- Interface: `http://192.168.178.60:6017/ui/`
- Artifact index: `http://192.168.178.60:6017/downloads/`
- Database starts empty and is populated only by real ESP32 heartbeats.
- Local HTTP is for private LAN development. No public HTTPS deployment exists.
- Public operation requires HTTPS with verified certificates, exact-origin CORS if origins differ, and the deployment items in `ISSUES.md` resolved.

## Project structure

| Path | Purpose |
| --- | --- |
| `Server/` | FastAPI application, Docker configuration, API tests, artifact index generator |
| `Interface/` | Real-data-only browser test interface served at `/ui/` |
| `Firmware/esp-race-test/` | ESP32 firmware, PlatformIO configuration, safe secrets template, manual flash guide |
| `SERVER_INFO.md` | Verified architecture, endpoints, deployment and test state |
| `CHANGELOG.md` | Dated project changes |
| `ISSUES.md` | Open and resolved issues |

## Server operation

The server operator should use the existing files in `Server/` as provided. If there is no valid local `Server/.env`, copy `Server/.env.example` to `Server/.env` and set distinct `DEVICE_API_KEY` and `ADMIN_API_KEY` values. Preserve existing valid keys. Keep `.env` outside Git and all ZIP archives. Then start the existing service with:

```sh
cd Server
docker compose up -d --build
```

The service should remain limited to the local network. Do not expose the development HTTP service to the public internet. Operational details and health checks are in `Server/README.md`.

## Firmware

See `Firmware/esp-race-test/README.md`. The ESP32 boards are flashed manually by the operator. The firmware sends actual heartbeats, polls real commands, and reports `peer_active=true` only after receiving actual ESP-NOW PING frames from the configured peer.

The tracked `secrets.example.h` contains placeholders only. Copy it to `secrets.h` locally and fill in Wi-Fi credentials and the device API key. The actual `secrets.h` must never be committed or included in an archive.

## Verification status

The current server/interface archive reports 34 passing Python tests and 8 passing interface logic tests. This repository adds the firmware source after that report. The Arduino/PlatformIO build and all hardware-dependent acceptance checks remain pending until the firmware toolchain and physical ESP32 boards are used. See `ISSUES.md` for exact status.
