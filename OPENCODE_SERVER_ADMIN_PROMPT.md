# OpenCode prompt: server administration only

The repository contains the complete application source. Your role in this task is server administration and deployment, not software development.

## Rules

- Do not create, rewrite, refactor, or patch application code, firmware, tests, or frontend assets.
- You may update only `SERVER_INFO.md`, `CHANGELOG.md`, and `ISSUES.md` to record verified operational results. Do not invent results or restructure these documents.
- Do not invent API routes, schemas, configuration files, or fallback behavior.
- Use the repository files as the source of truth. If they do not match the running server, report the exact difference and stop before changing source.
- You may perform server-administration actions needed to install or run the provided source, set filesystem permissions, create local secret files from the documented environment variable names, restart services, inspect logs, and run the existing tests.
- Never print, disclose, or include secret values in output, logs, screenshots, archives, or shell command arguments.
- Do not access, reset, erase, program, or flash physical ESP32 boards. The operator flashes and tests the devices manually.
- Do not expose the local HTTP service to the public internet. No public HTTPS origin currently exists.
- Do not update or publish the existing hosted page.

## Task

1. Inspect the provided repository and the current service state. Confirm the source branch/commit and report any differences from the running deployment.
2. Verify the local service at `http://192.168.178.60:6017`, the interface at `/ui/`, the health endpoint, and the artifact index at `/downloads/`.
3. If the exact provided source is already installed, do not recreate it. If deployment is needed, deploy the provided files as-is using the existing Docker Compose configuration. Preserve the runtime database and do not insert demo or test device data into it.
4. Confirm `Server/.env` exists with distinct `DEVICE_API_KEY` and `ADMIN_API_KEY` values without printing or copying those values. Do not generate replacements if valid secrets already exist.
5. Run the existing backend and interface tests from the documented commands. Use isolated test data only. Do not modify application files to make a test pass.
6. Verify that the runtime device list remains empty unless real ESP32 hardware has sent heartbeats.
7. Create the required per-task ZIP snapshot from the existing source and updated factual records. Exclude secrets, databases, runtime data, logs, caches, and generated firmware binaries. Verify the exact download URL returns HTTP 200 and a valid ZIP.
8. Update the three factual project records listed above and create the required per-task ZIP snapshot. Do not modify source files. If a server condition requires an application source change, report the exact file and reason as a blocker for the developer instead of editing it.

Report only verified results, exact URLs, test counts, deployment changes, and blockers. Do not claim that firmware or hardware acceptance checks passed unless the operator supplied real test evidence.
