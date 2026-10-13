# ESP32 firmware build and manual test

## Hardware and software

- Two ESP32 development boards supported by Arduino-ESP32 Core 3.x.
- Both boards use the same 2.4 GHz Wi-Fi network and channel.
- PlatformIO Core with the environment matching the board (`esp32dev` for a classic
  ESP32 Dev Module, `esp32-s3-devkitc-1` for that S3 board), or Arduino IDE with
  ArduinoJson 7.x.
- USB cable and the correct serial port selected manually by the operator.

## Configure credentials

Copy `secrets.example.h` to `secrets.h`. Fill in the Wi-Fi SSID, Wi-Fi password, and the exact `DEVICE_API_KEY` configured on the server. Use a different local `secrets.h` on each workstation as needed. The `.gitignore` excludes this file.

For the private LAN setup, keep the configured API origin at `http://192.168.178.60:6017`. HTTP is allowed only for this exact development origin and only when `RACE_ALLOW_LAN_HTTP` is set to `1`. Device keys travel unencrypted in this private LAN mode, so do not use it on an untrusted network or over the public internet.

For a public HTTPS deployment, set the HTTPS origin, configure a valid root CA PEM, and set `RACE_ALLOW_LAN_HTTP` to `0`. The firmware verifies the certificate and refuses HTTPS when the CA is missing. It never disables TLS verification.

## Build with PlatformIO

From this directory, after PlatformIO and its dependencies are installed, select the
environment matching the actual board. For a classic ESP32 Dev Module:

```sh
pio run -e esp32dev
```

For an ESP32-S3 DevKitC-1:

```sh
pio run -e esp32-s3-devkitc-1
```

The output firmware image is created under `.pio/build/<environment>/`. It is a
generated artifact and should not be committed. If the physical board is another
variant, select its exact board target before building.

## Build and flash manually in Arduino IDE

1. Install Arduino-ESP32 Core 3.x and ArduinoJson 7.x in Arduino IDE.
2. Open `esp-race-test.ino` from this directory.
3. Copy `secrets.example.h` to `secrets.h` and set local credentials.
4. Select the matching ESP32 board and USB port.
5. Compile, then flash the board manually.
6. Repeat for the second ESP32. Keep credentials out of screenshots and serial logs.

The firmware prints operational status only. It never prints Wi-Fi passwords or API keys.

## Expected manual checks

1. Open the server interface at `http://192.168.178.60:6017/ui/` and enter the admin key. The key remains in page memory only.
2. Flash and start ESP32 A. Within one polling interval it should appear with its actual MAC, Wi-Fi channel, RSSI, firmware, uptime, and last heartbeat.
3. Start ESP32 B and verify it appears independently.
4. Wait more than 15 seconds after stopping one board. Only that board should become offline.
5. Request pairing for A and B when both are online on the same channel. The server must create two commands. Each board should report the command acknowledgement.
6. The UI must not report the ESP-NOW connection as confirmed until both devices report reciprocal peer MACs and `peer_active=true` after actual PING reception.
7. Change channels or use a device on another channel. The API should reject the pairing with `409 wifi_channel_mismatch` and create no commands.
8. Reload the browser. Device state must be fetched again from the server; no device data should come from browser storage.

Record actual results, serial messages, API state, and any failures. Do not mark checks as passed based only on issuing a command or clicking a control.
