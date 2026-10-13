import {
  PAIRING_CODES_TO_MESSAGE,
  canPair,
  deviceHasPendingUnpair,
  eligibleForPairing,
  checkLabels,
  evaluateChecks,
  findConnectionConfirmed,
} from "./ui-logic.js";

const POLL_MS = 5000;
const THEME_KEY = "esp-race-test-color-mode";

const state = {
  adminKey: null,
  devices: [],
  events: [],
  pairings: [],
  devicesOk: false,
  serverStatus: "loading",
  lastGoodAt: null,
  seenOnlineIds: [],
  channelMismatchSeen: false,
  freshNavigationDevicesLoaded: false,
  authRequired: false,
  latched: {},
};

const $ = (selector) => document.querySelector(selector);

const elements = {
  status: $("[data-server-status]"),
  connectionState: $("[data-connection-state]"),
  lastFetch: $("[data-last-fetch]"),
  deviceList: $("[data-device-list]"),
  emptyDevices: $("[data-empty-devices]"),
  eventList: $("[data-event-list]"),
  emptyEvents: $("[data-empty-events]"),
  commandList: $("[data-command-list]"),
  checkList: $("[data-check-list]"),
  pairA: $("[data-pair-select=\"a\"]"),
  pairB: $("[data-pair-select=\"b\"]"),
  pairHint: $("[data-pair-hint]"),
  pairSubmit: $("[data-pair-submit]"),
  pairFeedback: $("[data-pair-feedback]"),
  authDialog: $("[data-auth-dialog]"),
  authForm: $("[data-auth-form]"),
  authError: $("[data-auth-error]"),
  authInput: $("[data-auth-input]"),
  templDevice: $("[data-tpl-device]"),
  templEvent: $("[data-tpl-event]"),
  templCommand: $("[data-tpl-command]"),
  stateCard: $("[data-connection-state]").parentElement,
};

const STATUS_TEXT = {
  loading: "Lade…",
  live: "Live",
  stale: "Server nicht erreichbar",
  auth: "Anmeldung nötig",
};

const STATUS_CLASS = {
  loading: "pill pill--mute",
  live: "pill",
  stale: "pill pill--danger",
  auth: "pill pill--warn",
};

const STATE_PILL = {
  pending: ["Befehl wartet (pending)", "pill pill--warn"],
  ack_ok: ["Befehl bestätigt (ack_ok)", "pill"],
  ack_failed: ["Befehl fehlgeschlagen (ack_failed)", "pill pill--danger"],
};

function isFreshNavigation() {
  const entries = performance.getEntriesByType("navigation");
  if (!entries || entries.length === 0) return false;
  const type = entries[0].type;
  return type === "reload" || type === "navigate";
}

state.freshNavigation = isFreshNavigation();

async function apiRequest(path, options = {}) {
  const { method = "GET", body = null, expectObject = false } = options;
  const headers = { "X-Admin-Key": state.adminKey };
  if (body !== null) {
    headers["Content-Type"] = "application/json";
  }
  let response;
  try {
    response = await fetch(path, { method, headers, body: body === null ? undefined : JSON.stringify(body) });
  } catch (error) {
    throw { kind: "network", source: path };
  }
  if (response.status === 401) {
    throw { kind: "auth", source: path };
  }
  let jsonBody = null;
  let parseError = false;
  if (response.status !== 204) {
    try {
      jsonBody = await response.json();
    } catch (error) {
      parseError = true;
    }
  }
  if (!response.ok) {
    if (parseError) {
      throw { kind: "invalid_response", status: response.status, source: path };
    }
    const detail = jsonBody && typeof jsonBody === "object" ? jsonBody.detail : null;
    throw {
      kind: "api_error",
      status: response.status,
      code: detail && typeof detail === "object" && detail.code ? detail.code : "unknown",
      message: detail && typeof detail === "object" && typeof detail.message === "string" ? detail.message : "",
      source: path,
    };
  }
  if (parseError) {
    throw { kind: "invalid_response", status: response.status, source: path };
  }
  if (expectObject) {
    if (jsonBody === null || typeof jsonBody !== "object") {
      throw { kind: "invalid_response", status: response.status, source: path };
    }
    return jsonBody;
  }
  if (!Array.isArray(jsonBody)) {
    throw { kind: "invalid_response", status: response.status, source: path };
  }
  return jsonBody;
}

function requireAuth(message) {
  state.authRequired = true;
  state.serverStatus = "auth";
  if (message) {
    elements.authError.textContent = message;
    elements.authError.hidden = false;
    elements.authDialog.showModal();
  }
  render();
}

function rememberOnlineDevices() {
  for (const device of state.devices) {
    if (device.online === true && !state.seenOnlineIds.includes(device.id)) {
      state.seenOnlineIds.push(device.id);
    }
  }
}

function setFeedback(text, tone) {
  elements.pairFeedback.textContent = text;
  elements.pairFeedback.className = `feedback${tone ? ` feedback--${tone}` : ""}`;
}

async function poll() {
  if (state.authRequired) return;
  const [devicesResult, eventsResult, pairingsResult] = await Promise.allSettled([
    apiRequest("/api/v1/devices"),
    apiRequest("/api/v1/events?limit=200"),
    apiRequest("/api/v1/pairings"),
  ]);
  const rejected = [devicesResult, eventsResult, pairingsResult].some((result) => result.status === "rejected");
  if (rejected) {
    const reason = [devicesResult, eventsResult, pairingsResult]
      .find((result) => result.status === "rejected")?.reason ?? {};
    if (reason.kind === "auth") {
      requireAuth("Zugriff verweigert: Admin-Key ungültig (401).");
      return;
    }
    state.serverStatus = "stale";
    render();
    return;
  }
  state.devices = devicesResult.value;
  state.events = eventsResult.value;
  state.pairings = pairingsResult.value;
  state.devicesOk = true;
  state.lastGoodAt = new Date();
  state.serverStatus = "live";
  rememberOnlineDevices();
  if (state.freshNavigation && state.devices.length > 0) {
    state.freshNavigationDevicesLoaded = true;
  }
  render();
}

function renderStatus() {
  elements.status.textContent = STATUS_TEXT[state.serverStatus] || "—";
  elements.status.className = STATUS_CLASS[state.serverStatus] || "pill pill--mute";
  if (state.serverStatus === "stale") {
    elements.connectionState.textContent = "Server nicht erreichbar – angezeigt werden die zuletzt erfolgreich empfangenen Daten, nicht der aktuelle Zustand.";
    elements.connectionState.className = "state-line feedback--error";
  } else if (state.serverStatus === "live") {
    elements.connectionState.textContent = "Verbindung hergestellt (Poll alle 5 s)";
    elements.connectionState.className = "state-line";
  } else if (state.serverStatus === "auth") {
    elements.connectionState.textContent = "Admin-Key wird benötigt.";
    elements.connectionState.className = "state-line feedback--error";
  } else {
    elements.connectionState.textContent = "Lade…";
    elements.connectionState.className = "state-line";
  }
  if (state.lastGoodAt) {
    elements.lastFetch.hidden = false;
    elements.lastFetch.textContent = `Letzte erfolgreiche Abfrage: ${state.lastGoodAt.toLocaleTimeString("de-DE")}${state.serverStatus === "stale" ? " (veraltet)" : ""}`;
  }
}

function renderDevices() {
  elements.deviceList.replaceChildren();
  elements.emptyDevices.hidden = state.devices.length !== 0;
  for (const device of state.devices) {
    const node = elements.templDevice.content.cloneNode(true);
    node.querySelector("[data-device-id]").dataset.deviceId = device.id;
    node.querySelector("[data-d-id]").textContent = device.id;
    node.querySelector("[data-d-online]").hidden = device.online !== true;
    node.querySelector("[data-d-offline]").hidden = device.online === true;
    node.querySelector("[data-d-channel]").textContent = device.wifi_channel == null ? "—" : String(device.wifi_channel);
    node.querySelector("[data-d-rssi]").textContent = `${device.wifi_rssi} dBm`;
    node.querySelector("[data-d-uptime]").textContent = device.uptime_ms == null ? "—" : `${Math.max(0, Math.round(device.uptime_ms / 1000))} s`;
    node.querySelector("[data-d-firmware]").textContent = device.firmware || "—";
    node.querySelector("[data-d-peer]").textContent = device.peer_mac || "—";
    node.querySelector("[data-d-last-seen]").textContent = formatTimestamp(device.last_seen);
    const peerActive = node.querySelector("[data-d-peer-active]");
    peerActive.textContent = device.peer_active === true ? "ja" : "nein";
    const unpairButton = node.querySelector("[data-d-unpair]");
    if (deviceHasPendingUnpair(state.pairings, device.id)) {
      unpairButton.disabled = true;
      unpairButton.textContent = "Trennung wartet";
    } else {
      unpairButton.disabled = !device.peer_mac;
      unpairButton.textContent = "Trennen";
      unpairButton.addEventListener("click", () => { void requestUnpair(device.id); });
    }
    elements.deviceList.append(node);
  }
}

function renderEvents() {
  elements.eventList.replaceChildren();
  elements.emptyEvents.hidden = state.events.length !== 0;
  for (const event of state.events.slice(0, 100)) {
    const node = elements.templEvent.content.cloneNode(true);
    node.querySelector("[data-e-time]").textContent = event.ts;
    node.querySelector("[data-e-device]").textContent = event.device_id;
    node.querySelector("[data-e-type]").textContent = event.type;
    node.querySelector("[data-e-json]").textContent = JSON.stringify(event.details ?? null);
    elements.eventList.append(node);
  }
}

function renderCommands() {
  elements.commandList.replaceChildren();
  const commands = [...state.pairings].sort((a, b) => String(a.created_at).localeCompare(String(b.created_at)));
  for (const command of commands.slice(-12).reverse()) {
    const node = elements.templCommand.content.cloneNode(true);
    node.querySelector("[data-c-device]").textContent = command.device_id;
    node.querySelector("[data-c-action]").textContent = command.action;
    node.querySelector("[data-c-peer]").textContent = command.action === "pair" ? `→ ${command.peer_mac}` : "";
    const statePill = node.querySelector("[data-c-state]");
    const [text, className] = STATE_PILL[command.state] || [command.state, "pill pill--mute"];
    statePill.textContent = text;
    statePill.className = className;
    elements.commandList.append(node);
  }
}

function renderPairingPanel() {
  const eligible = state.devices.filter(eligibleForPairing);
  fillPairSelect(elements.pairA, eligible, elements.pairA.value);
  const a = state.devices.find((device) => device.id === elements.pairA.value);
  const eligiblePartners = a
    ? eligible.filter((device) => device.id !== a.id && device.wifi_channel === a.wifi_channel)
    : eligible;
  fillPairSelect(elements.pairB, eligiblePartners, elements.pairB.value);
  const b = state.devices.find((device) => device.id === elements.pairB.value);
  const ready = canPair(a, b);
  elements.pairSubmit.disabled = !ready;
  if (ready) {
    elements.pairHint.textContent = `Bereit: beide Geräte online auf Kanal ${a.wifi_channel}.`;
  } else if (a && eligible.length >= 2 && eligiblePartners.length === 0) {
    elements.pairHint.textContent = `Kein weiteres online gemeldetes Gerät auf Kanal ${a.wifi_channel}. Geräte auf anderen Kanälen können nicht gekoppelt werden.`;
  } else if (eligible.length < 2) {
    elements.pairHint.textContent = "Kopplung nur möglich, wenn serverseitig mindestens zwei Geräte online sind und denselben WLAN-Kanal melden.";
  } else {
    elements.pairHint.textContent = "Kopplung nur für Geräte mit gleichem WLAN-Kanal, die der Server als online meldet.";
  }
}

function formatTimestamp(value) {
  if (typeof value !== "string" || value.length === 0) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("de-DE");
}

function fillPairSelect(select, eligible, previousValue) {
  select.replaceChildren();
  for (const device of eligible) {
    const option = document.createElement("option");
    option.value = device.id;
    option.textContent = `${device.id} (Kanal ${device.wifi_channel})`;
    select.append(option);
  }
  if (eligible.some((device) => device.id === previousValue)) {
    select.value = previousValue;
  }
}

function renderChecks() {
  const computed = evaluateChecks({
    devices: state.devices,
    devicesOk: state.devicesOk,
    seenOnlineIds: state.seenOnlineIds,
    channelMismatchSeen: state.channelMismatchSeen,
    freshNavigationDevicesLoaded: state.freshNavigationDevicesLoaded,
    pairings: state.pairings,
  });
  elements.checkList.replaceChildren();
  for (const entry of computed) {
    const passed = state.latched[entry.id] === "passed" || entry.status === "passed";
    state.latched[entry.id] = passed ? "passed" : entry.status;
    const item = document.createElement("li");
    item.className = `check${passed ? " check--passed" : ""}`;
    const id = document.createElement("span");
    id.className = "check__id";
    id.textContent = entry.id.toUpperCase();
    const status = document.createElement("span");
    status.className = passed ? "pill" : "pill pill--mute";
    status.textContent = passed ? "bestanden" : "offen";
    const label = document.createElement("span");
    label.textContent = entry.label;
    const evidence = document.createElement("span");
    evidence.className = "check__evidence";
    evidence.textContent = entry.evidence;
    item.append(id, status, label, evidence);
    elements.checkList.append(item);
  }
}

function renderConnectionBanner() {
  let banner = document.getElementById("connection-banner");
  if (!banner) {
    banner = document.createElement("p");
    banner.id = "connection-banner";
    banner.className = "state-line feedback--ok";
    banner.setAttribute("role", "status");
    elements.stateCard.append(banner);
  }
  const confirmed = findConnectionConfirmed(state.devices);
  banner.hidden = !confirmed;
  banner.textContent = confirmed
    ? `ESP-NOW-Verbindung bestätigt: ${confirmed[0].id} ↔ ${confirmed[1].id}`
    : "";
}

function render() {
  renderStatus();
  renderDevices();
  renderEvents();
  renderCommands();
  renderPairingPanel();
  renderChecks();
  renderConnectionBanner();
}

async function requestPairing() {
  const first = elements.pairA.value;
  const second = elements.pairB.value;
  if (!state.adminKey || state.authRequired) {
    requireAuth("Zugriff verweigert: kein Admin-Key eingegeben.");
    return;
  }
  if (!first || !second || first === second) return;
  elements.pairHint.textContent = "Kopplung wird angefragt…";
  try {
    const body = await apiRequest("/api/v1/pairings", { method: "POST", body: { first, second }, expectObject: true });
    setFeedback(`Befehl wartet (pending): ${body.commands.length} Commands für ${body.pairing_id} erzeugt.`, "ok");
  } catch (error) {
    handlePairingError(error);
  } finally {
    await poll();
  }
}

function handlePairingError(error) {
  if (error.kind === "auth") {
    requireAuth("Zugriff verweigert: Admin-Key ungültig (401).");
    return;
  }
  if (error.kind === "network") {
    setFeedback("Server nicht erreichbar: Kopplung wurde nicht ausgelöst.", "error");
    return;
  }
  if (error.kind === "invalid_response") {
    setFeedback(`Ungültige Serverantwort (HTTP ${error.status ?? "?"}).`, "error");
    return;
  }
  if (error.kind === "api_error") {
    if (error.status === 409 && error.code === "wifi_channel_mismatch") {
      state.channelMismatchSeen = true;
    }
    const mapped = PAIRING_CODES_TO_MESSAGE[error.code];
    setFeedback(`Abgelehnt (HTTP ${error.status} ${error.code}): ${mapped || error.message || "unbekannter Fehler."}`, "error");
    return;
  }
  setFeedback("Unbekannter Fehler bei der Kopplungsanfrage.", "error");
}

async function requestUnpair(deviceId) {
  if (!state.adminKey || state.authRequired) {
    requireAuth("Zugriff verweigert: kein Admin-Key eingegeben.");
    return;
  }
  try {
    await apiRequest(`/api/v1/unpair/${encodeURIComponent(deviceId)}`, { method: "POST", expectObject: true });
    setFeedback("Trennung: Befehl wartet (pending).", "ok");
  } catch (error) {
    handlePairingError(error);
  } finally {
    await poll();
  }
}

elements.authForm.addEventListener("submit", (event) => {
  event.preventDefault();
  state.adminKey = String(new FormData(elements.authForm).get("admin-key") || "");
  if (!state.adminKey) return;
  state.authRequired = false;
  elements.authError.hidden = true;
  elements.authDialog.close();
  elements.authInput.value = "";
  void poll();
});

elements.pairSubmit.addEventListener("click", () => { void requestPairing(); });
elements.pairA.addEventListener("change", renderPairingPanel);
elements.pairB.addEventListener("change", renderPairingPanel);

$("[data-theme-toggle]").addEventListener("click", () => {
  const next = document.documentElement.dataset.colorMode === "light" ? "dark" : "light";
  document.documentElement.dataset.colorMode = next;
  try { localStorage.setItem(THEME_KEY, next); } catch {}
});

void poll();
setInterval(() => { void poll(); }, POLL_MS);

if (!state.adminKey) {
  elements.authDialog.showModal();
}

render();
