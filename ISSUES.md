# ISSUES — esp-race-test

## Open

| ID | Issue | Reason / missing prerequisite | Status |
| --- | --- | --- | --- |
| ISSUE-01 | Public HTTPS deployment (`RACE_API_ORIGIN`) does not exist | No public host/domain/TLS setup yet; must be provided before firmware can verify certificates | open |
| ISSUE-02 | Actual `FRONTEND_ORIGIN` undecided | Interface is currently same-origin; only relevant if browser and API split | open |
| ISSUE-03 | Reverse proxy with `/api/` forwarding, header pass-through, preflight | Not present; needed when origins diverge or for TLS termination | open |
| ISSUE-04 | CORS allowlist | Disabled by design (same-origin); must be set to the exact frontend origin if ISSUE-02 changes | open |
| ISSUE-05 | Firmware source not compiled; TLS/certificate config unverified | PlatformIO is unavailable in this environment; public HTTPS origin and CA chain are also absent | open, blocked by toolchain and ISSUE-01 |
| ISSUE-06 | Acceptance checks 2–8 not hardware-verified | No ESP32 devices connected; interface can only evaluate checks from real device/server data | open, blocked by hardware |
| ISSUE-07 | Browser interaction test of rendered interface in a real browser was not performed | No headless-browser test harness installed; logic + serving + contract covered by Node/pytest tests instead | open |
| ISSUE-08 | Exact ESP32 board variant is not confirmed | Two PlatformIO profiles are included, classic ESP32 Dev Module and ESP32-S3 DevKitC-1; select or add the exact target matching the physical boards before compiling | open |

## Resolved

| ID | Issue | Resolution |
| --- | --- | --- |
| RES-01 | Schema initialization ordering bug (indexes before table) | Fixed in M1 before first successful startup |
| RES-02 | Runtime DB contained manual smoke data after M2 | Reset to empty in M3 (fresh files + restart); verified `[]` |
| RES-03 | Docker test volume auto-created as root → container crash loop | Fixture pre-creates bind-mount dir with host uid (M3) |
| RES-04 | Runtime DB accidentally deleted under running container → 500s | Documented ops note (restart required after manual DB removal); database reset properly |
| RES-05 | `/downloads/` reported "not reachable" | Root cause: bare endpoint returned 404 (no directory index); the exact ZIP file URL returned 200 byte-identical all along. Fixed by generated `artifacts/index.html` + `html=True` on the mount. Verified: HTTP 200 on `/downloads/` and file URL, valid ZIP archive, matching SHA-256, from host LAN IP and a separate network namespace via the DNAT port-forward path. Unverified: physical second LAN device (none available); base-URL reachability from LAN clients already confirmed by user, ruling out per-path filtering. |
| RES-06 | Artifact directory had no listing | `Server/scripts/artifacts_index.py` regenerates `artifacts/index.html` each packaging run; endpoint serves only that dedicated directory |

## None blocked this milestone

M4 completed without unresolved blockers on its own scope; remaining items above belong to deployment (M-later), firmware (M5), and real hardware.
