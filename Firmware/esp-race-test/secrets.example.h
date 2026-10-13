#pragma once

// Copy this file to secrets.h and fill in local values.
// secrets.h is excluded from Git and all project ZIP snapshots.
#define WIFI_SSID "REPLACE_WITH_WIFI_SSID"
#define WIFI_PASSWORD "REPLACE_WITH_WIFI_PASSWORD"
#define DEVICE_API_KEY "REPLACE_WITH_DEVICE_API_KEY"

// Private development server. LAN HTTP is permitted only for this exact origin.
#define RACE_API_BASE_URL "http://192.168.178.60:6017"
#define RACE_ALLOW_LAN_HTTP 1

// For HTTPS deployments, set a valid PEM root CA here and set RACE_ALLOW_LAN_HTTP to 0.
// Never disable certificate validation.
#define RACE_ROOT_CA_PEM ""
