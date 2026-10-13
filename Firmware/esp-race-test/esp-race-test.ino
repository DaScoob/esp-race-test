/*
 * ESP Race test firmware for ESP32, Arduino-ESP32 Core 3.x.
 *
 * This firmware talks directly to the FastAPI backend. It does not depend on
 * the browser interface. Copy secrets.example.h to secrets.h and configure it
 * before compiling. secrets.h contains credentials and must not be committed.
 */

#include <Arduino.h>
#include <ArduinoJson.h>
#include <ctype.h>
#include <HTTPClient.h>
#include <stdlib.h>
#include <string.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_now.h>
#include <esp_wifi.h>

#include "secrets.h"

#if !defined(WIFI_SSID) || !defined(WIFI_PASSWORD) || !defined(DEVICE_API_KEY) || !defined(RACE_API_BASE_URL) || !defined(RACE_ROOT_CA_PEM)
#error "Configure Wi-Fi, device key, API URL, and ROOT_CA_PEM in secrets.h"
#endif

namespace {
constexpr char FIRMWARE_VERSION[] = "0.2.0";
constexpr uint32_t HEARTBEAT_INTERVAL_MS = 5000;
constexpr uint32_t COMMAND_POLL_INTERVAL_MS = 1500;
constexpr uint32_t PING_INTERVAL_MS = 1000;
constexpr uint32_t PEER_ACTIVE_WINDOW_MS = 6000;
constexpr uint32_t WIFI_RETRY_INTERVAL_MS = 10000;
constexpr uint32_t PING_MAGIC = 0x45535052;  // "ESPR"

struct __attribute__((packed)) PingFrame {
  uint32_t magic;
  uint32_t sequence;
};

String deviceId;
uint8_t peerMac[6] = {};
bool peerConfigured = false;
bool espNowReady = false;
uint32_t lastPeerPingMs = 0;
portMUX_TYPE peerStateMux = portMUX_INITIALIZER_UNLOCKED;
uint32_t nextHeartbeatMs = 0;
uint32_t nextCommandPollMs = 0;
uint32_t nextPingMs = 0;
uint32_t nextWifiRetryMs = 0;
uint32_t pingSequence = 0;
int lastWifiChannel = 0;

bool due(uint32_t now, uint32_t deadline) {
  return static_cast<int32_t>(now - deadline) >= 0;
}

bool isHex(char c) {
  return (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') || (c >= 'a' && c <= 'f');
}

bool normalizeMac(const String& input, String& output) {
  output = "";
  output.reserve(12);
  for (size_t i = 0; i < input.length(); ++i) {
    const char c = input[i];
    if (c == ':' || c == '-') continue;
    if (!isHex(c)) return false;
    output += static_cast<char>(toupper(c));
  }
  return output.length() == 12;
}

bool parseMac(const String& input, uint8_t output[6]) {
  String normalized;
  if (!normalizeMac(input, normalized)) return false;
  for (size_t i = 0; i < 6; ++i) {
    char byteText[3] = {normalized[i * 2], normalized[i * 2 + 1], '\0'};
    output[i] = static_cast<uint8_t>(strtoul(byteText, nullptr, 16));
  }
  return true;
}

String macToString(const uint8_t mac[6]) {
  char text[13];
  snprintf(text, sizeof(text), "%02X%02X%02X%02X%02X%02X",
           mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);
  return String(text);
}

bool copyConfiguredPeer(uint8_t output[6]) {
  portENTER_CRITICAL(&peerStateMux);
  const bool configured = peerConfigured;
  if (configured) memcpy(output, peerMac, sizeof(peerMac));
  portEXIT_CRITICAL(&peerStateMux);
  return configured;
}

void clearPeerPingTime() {
  portENTER_CRITICAL(&peerStateMux);
  lastPeerPingMs = 0;
  portEXIT_CRITICAL(&peerStateMux);
}

bool isConfiguredHttpOrigin(const String& baseUrl) {
#if defined(RACE_ALLOW_LAN_HTTP) && RACE_ALLOW_LAN_HTTP == 1
  return baseUrl == "http://192.168.178.60:6017";
#else
  (void)baseUrl;
  return false;
#endif
}

bool request(const char* method, const String& path, const String& payload, String& responseBody) {
  if (WiFi.status() != WL_CONNECTED) return false;

  const String baseUrl = String(RACE_API_BASE_URL);
  const bool useTls = baseUrl.startsWith("https://");
  if (!useTls && (!baseUrl.startsWith("http://") || !isConfiguredHttpOrigin(baseUrl))) {
    Serial.println("Refusing API URL: HTTP is allowed only for the configured private LAN origin.");
    return false;
  }

  HTTPClient http;
  http.setConnectTimeout(3000);
  http.setTimeout(4000);
  const String url = baseUrl + path;
  WiFiClient plainClient;
  WiFiClientSecure tlsClient;

  bool started = false;
  if (useTls) {
    const char* ca = RACE_ROOT_CA_PEM;
    if (ca == nullptr || strlen(ca) < 100) {
      Serial.println("HTTPS refused: a valid trusted ROOT CA PEM is not configured.");
      return false;
    }
    tlsClient.setCACert(ca);
    started = http.begin(tlsClient, url);
  } else {
    started = http.begin(plainClient, url);
  }

  if (!started) {
    Serial.println("Could not initialize HTTP request.");
    return false;
  }

  http.addHeader("X-Device-Key", DEVICE_API_KEY);
  int status = 0;
  if (strcmp(method, "POST") == 0) {
    http.addHeader("Content-Type", "application/json");
    status = http.POST(payload);
  } else {
    status = http.GET();
  }
  if (status > 0) responseBody = http.getString();
  http.end();

  if (status < 200 || status >= 300) {
    Serial.printf("API request failed: HTTP %d on %s\n", status, path.c_str());
    return false;
  }
  return true;
}

bool postJson(const String& path, JsonDocument& document, String& responseBody) {
  String payload;
  serializeJson(document, payload);
  return request("POST", path, payload, responseBody);
}

void postEvent(const char* type, const char* detailKey, const String& detailValue) {
  JsonDocument document;
  document["device_id"] = deviceId;
  document["type"] = type;
  document["details"][detailKey] = detailValue;
  String responseBody;
  postJson("/api/v1/events", document, responseBody);
}

bool peerIsActive(uint32_t now) {
  portENTER_CRITICAL(&peerStateMux);
  const bool configured = peerConfigured;
  const uint32_t receivedAt = lastPeerPingMs;
  portEXIT_CRITICAL(&peerStateMux);
  return configured && receivedAt != 0 && static_cast<uint32_t>(now - receivedAt) < PEER_ACTIVE_WINDOW_MS;
}

bool ensureEspNow() {
  if (espNowReady) return true;
  if (esp_now_init() != ESP_OK) {
    Serial.println("ESP-NOW initialization failed.");
    return false;
  }
  esp_now_register_recv_cb([](const esp_now_recv_info_t* info, const uint8_t* data, int length) {
    if (!info || !data || length != static_cast<int>(sizeof(PingFrame))) return;
    PingFrame frame{};
    memcpy(&frame, data, sizeof(frame));
    if (frame.magic != PING_MAGIC) return;
    portENTER_CRITICAL(&peerStateMux);
    if (peerConfigured && memcmp(info->src_addr, peerMac, sizeof(peerMac)) == 0) {
      lastPeerPingMs = millis();
    }
    portEXIT_CRITICAL(&peerStateMux);
  });
  espNowReady = true;
  return true;
}

bool configurePeer(const String& input) {
  uint8_t targetMac[6] = {};
  String normalized;
  if (!normalizeMac(input, normalized) || !parseMac(normalized, targetMac) || normalized == deviceId) {
    return false;
  }
  if (!ensureEspNow()) return false;
  uint8_t currentPeer[6] = {};
  if (copyConfiguredPeer(currentPeer) && memcmp(currentPeer, targetMac, sizeof(currentPeer)) == 0) return true;

  if (copyConfiguredPeer(currentPeer)) {
    const esp_err_t removeResult = esp_now_del_peer(currentPeer);
    if (removeResult != ESP_OK && removeResult != ESP_ERR_ESPNOW_NOT_FOUND) return false;
    portENTER_CRITICAL(&peerStateMux);
    peerConfigured = false;
    lastPeerPingMs = 0;
    portEXIT_CRITICAL(&peerStateMux);
  }

  esp_now_peer_info_t info = {};
  memcpy(info.peer_addr, targetMac, sizeof(targetMac));
  info.channel = 0;  // Use the current Wi-Fi channel.
  info.ifidx = WIFI_IF_STA;
  info.encrypt = false;
  const esp_err_t addResult = esp_now_add_peer(&info);
  if (addResult != ESP_OK && addResult != ESP_ERR_ESPNOW_EXIST) return false;
  portENTER_CRITICAL(&peerStateMux);
  memcpy(peerMac, targetMac, sizeof(peerMac));
  lastPeerPingMs = 0;
  peerConfigured = true;
  portEXIT_CRITICAL(&peerStateMux);
  return true;
}

bool removePeer(const String& requestedPeer) {
  String requested;
  if (requestedPeer.length() && !normalizeMac(requestedPeer, requested)) return false;
  uint8_t currentPeer[6] = {};
  if (!copyConfiguredPeer(currentPeer)) return true;
  if (requested.length() && requested != macToString(currentPeer)) return false;
  const esp_err_t result = esp_now_del_peer(currentPeer);
  if (result != ESP_OK && result != ESP_ERR_ESPNOW_NOT_FOUND) return false;
  portENTER_CRITICAL(&peerStateMux);
  peerConfigured = false;
  memset(peerMac, 0, sizeof(peerMac));
  lastPeerPingMs = 0;
  portEXIT_CRITICAL(&peerStateMux);
  return true;
}

bool sendAck(const String& commandId, bool success, const String& detail) {
  JsonDocument document;
  document["device_id"] = deviceId;
  document["command_id"] = commandId;
  document["success"] = success;
  document["detail"] = detail;
  String responseBody;
  return postJson("/api/v1/commands/ack", document, responseBody);
}

void handleCommand() {
  String responseBody;
  const String path = String("/api/v1/commands?device_id=") + deviceId;
  if (!request("GET", path, "", responseBody)) return;

  JsonDocument response;
  if (deserializeJson(response, responseBody)) {
    Serial.println("Invalid command response JSON.");
    return;
  }
  JsonVariantConst command = response["command"];
  if (command.isNull()) return;

  const String commandId = command["command_id"] | "";
  const String action = command["action"] | "";
  const String peer = command["peer_mac"] | "";
  if (commandId.isEmpty()) {
    Serial.println("Command response has no command_id.");
    return;
  }

  bool success = false;
  String detail;
  if (action == "pair") {
    success = configurePeer(peer);
    detail = success ? "ESP-NOW peer configured; waiting for real peer PING" : "ESP-NOW peer configuration failed";
  } else if (action == "unpair") {
    success = removePeer(peer);
    detail = success ? "Peer removed" : "Requested peer does not match configured peer or removal failed";
  } else {
    detail = "Unsupported command action";
  }

  Serial.printf("Command %s: %s\n", commandId.c_str(), success ? "applied" : "failed");
  if (sendAck(commandId, success, detail)) {
    postEvent(success ? "command_ok" : "command_failed", "command_id", commandId);
  }
}

void sendHeartbeat() {
  JsonDocument document;
  document["device_id"] = deviceId;
  document["firmware"] = FIRMWARE_VERSION;
  document["wifi_rssi"] = WiFi.RSSI();
  document["wifi_channel"] = WiFi.channel();
  document["uptime_ms"] = millis();
  uint8_t currentPeer[6] = {};
  document["peer_mac"] = copyConfiguredPeer(currentPeer) ? macToString(currentPeer) : "";
  document["peer_active"] = peerIsActive(millis());
  String responseBody;
  if (postJson("/api/v1/heartbeat", document, responseBody)) {
    Serial.printf("Heartbeat sent, channel %d, peer active: %s\n",
                  WiFi.channel(), peerIsActive(millis()) ? "yes" : "no");
  }
}

void sendPing() {
  uint8_t currentPeer[6] = {};
  if (!copyConfiguredPeer(currentPeer) || !espNowReady || WiFi.status() != WL_CONNECTED) return;
  PingFrame frame{PING_MAGIC, ++pingSequence};
  const esp_err_t result = esp_now_send(currentPeer, reinterpret_cast<const uint8_t*>(&frame), sizeof(frame));
  if (result != ESP_OK) Serial.printf("ESP-NOW PING send failed: %d\n", static_cast<int>(result));
}

void startWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  nextWifiRetryMs = millis() + WIFI_RETRY_INTERVAL_MS;
  Serial.println("Connecting to configured Wi-Fi.");
}

bool configLooksValid() {
  const String ssid = WIFI_SSID;
  const String key = DEVICE_API_KEY;
  if (ssid.isEmpty() || ssid.startsWith("REPLACE_")) return false;
  if (key.length() < 32 || key.startsWith("REPLACE_")) return false;
  const String baseUrl = RACE_API_BASE_URL;
  return baseUrl.startsWith("https://") || isConfiguredHttpOrigin(baseUrl);
}
}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  if (!configLooksValid()) {
    Serial.println("Configuration incomplete or unsafe. Review secrets.h; no credentials are displayed.");
    while (true) delay(1000);
  }
  startWifi();
}

void loop() {
  const uint32_t now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (due(now, nextWifiRetryMs)) {
      WiFi.reconnect();
      nextWifiRetryMs = now + WIFI_RETRY_INTERVAL_MS;
    }
    delay(20);
    return;
  }

  const int currentChannel = WiFi.channel();
  if (!espNowReady) {
    if (ensureEspNow()) {
      if (!normalizeMac(WiFi.macAddress(), deviceId)) {
        Serial.println("Could not normalize the Wi-Fi station MAC address.");
        delay(1000);
        return;
      }
      lastWifiChannel = currentChannel;
      sendHeartbeat();
      postEvent("boot", "firmware", String(FIRMWARE_VERSION));
      nextHeartbeatMs = now + HEARTBEAT_INTERVAL_MS;
      nextCommandPollMs = now + COMMAND_POLL_INTERVAL_MS;
    }
  } else if (currentChannel != lastWifiChannel) {
    lastWifiChannel = currentChannel;
    uint8_t currentPeer[6] = {};
    if (copyConfiguredPeer(currentPeer)) {
      clearPeerPingTime();
      postEvent("wifi_channel_changed", "wifi_channel", String(currentChannel));
    }
  }

  if (due(now, nextHeartbeatMs)) {
    nextHeartbeatMs = now + HEARTBEAT_INTERVAL_MS;
    sendHeartbeat();
  }
  if (due(now, nextCommandPollMs)) {
    nextCommandPollMs = now + COMMAND_POLL_INTERVAL_MS;
    handleCommand();
  }
  if (due(now, nextPingMs)) {
    nextPingMs = now + PING_INTERVAL_MS;
    sendPing();
  }
  delay(10);
}
