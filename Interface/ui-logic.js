export const PAIRING_CODES_TO_MESSAGE = {
  device_offline: "Mindestens ein Gerät ist dem Server unbekannt oder seit mehr als 15 Sekunden ohne Heartbeat.",
  wifi_channel_mismatch: "Kanalabweichung: beide Geräte müssen denselben WLAN-Kanal melden.",
  same_device: "Zwei identische Geräte-IDs können nicht gekoppelt werden.",
  invalid_mac: "Ungültige Geräte-ID (12-stellige hexadezimale WLAN-MAC erwartet).",
  invalid_request: "Ungültige Anfrage.",
};

export function eligibleForPairing(device) {
  return Boolean(device)
    && device.online === true
    && typeof device.wifi_channel === "number"
    && Number.isFinite(device.wifi_channel);
}

export function canPair(deviceA, deviceB) {
  if (!deviceA || !deviceB || deviceA.id === deviceB.id) return false;
  return eligibleForPairing(deviceA) && eligibleForPairing(deviceB)
    && deviceA.wifi_channel === deviceB.wifi_channel;
}

export function findConnectionConfirmed(devices) {
  for (const a of devices) {
    for (const b of devices) {
      if (a.id >= b.id) continue;
      const reciprocal = a.online === true && b.online === true
        && a.peer_active === true && b.peer_active === true
        && a.peer_mac === b.id && b.peer_mac === a.id;
      if (reciprocal) return [a, b];
    }
  }
  return null;
}

export function commandsForPairing(commands, pairingId) {
  return commands.filter((command) => command.pairing_id === pairingId);
}

export function pairingAckState(commands, pairingId) {
  const two = commandsForPairing(commands, pairingId);
  if (two.length !== 2) return null;
  const states = new Set(two.map((command) => command.state));
  if (states.has("ack_failed")) return "ack_failed";
  if (states.has("pending")) return "pending";
  return "ack_ok";
}

export function deviceHasPendingUnpair(commands, deviceId) {
  return commands.some((command) => command.device_id === deviceId
    && command.action === "unpair" && command.state === "pending");
}

const CHECK_LABELS = [
  ["check-1", "Leere Datenbank: Interface zeigt „Keine echten Geräte registriert“"],
  ["check-2", "Gerät A erscheint beim nächsten 5-Sekunden-Poll als online"],
  ["check-3", "Gerät B erscheint beim nächsten 5-Sekunden-Poll als online"],
  ["check-4", "Mehr als 15 s ohne Heartbeat: nur dieses Gerät wird offline gemeldet"],
  ["check-5", "Pairing-Anfrage erzeugt zwei echte Commands mit gemeinsamem pairing_id"],
  ["check-6", "bestätigt die Kopplung nur nach acks und wechselseitigem peer_active/peer_mac"],
  ["check-7", "Unterschiedliche Kanäle: 409 Kanalabweichung wird verständlich gemeldet"],
  ["check-8", "Nach Neuladen des Browsers werden echte Geräte erneut vom Server geladen"],
];

export function checkLabels() {
  return CHECK_LABELS.map(([id, label]) => ({ id, label }));
}

function onlineDevices(devices) {
  return devices.filter((device) => device.online === true);
}

export function evaluateChecks(input) {
  const { devices, devicesOk, seenOnlineIds, channelMismatchSeen, freshNavigationDevicesLoaded } = input;
  const online = onlineDevices(devices);
  const offlineSeen = [...seenOnlineIds]
    .filter((id) => devices.some((device) => device.id === id && device.online !== true));
  const pairingGroups = new Map();
  for (const command of input.pairings || []) {
    if (command.action !== "pair" || !command.pairing_id) continue;
    const group = pairingGroups.get(command.pairing_id) || [];
    group.push(command);
    pairingGroups.set(command.pairing_id, group);
  }
  const completePairings = [...pairingGroups.entries()].filter(([, commands]) => {
    if (commands.length !== 2) return false;
    const [first, second] = commands;
    return first.command_id !== second.command_id
      && first.device_id !== second.device_id
      && first.peer_mac === second.device_id
      && second.peer_mac === first.device_id;
  });
  const confirmedPair = findConnectionConfirmed(devices);
  let ackOkSeen = false;
  if (confirmedPair) {
    const pairingIds = new Set(
      (input.pairings || [])
        .filter((command) => command.state === "ack_ok"
          && [command.device_id, command.peer_mac].sort().join("|")
            === [confirmedPair[0].id, confirmedPair[1].id].sort().join("|"))
        .map((command) => command.pairing_id),
    );
    ackOkSeen = [...pairingIds].some((pairingId) => {
      const state = pairingAckState(input.pairings || [], pairingId);
      return state === "ack_ok";
    });
  }
  const results = [
    { id: "check-1", status: devicesOk && devices.length === 0 ? "passed" : "pending", evidence: devicesOk ? `${devices.length} Geräte vom Server` : "kein Serverergebnis" },
    { id: "check-2", status: online.length >= 1 ? "passed" : "pending", evidence: online.length ? `${online.length} online` : "kein Gerät online" },
    { id: "check-3", status: online.length >= 2 ? "passed" : "pending", evidence: online.length >= 2 ? online.slice(0, 2).map((device) => device.id).join(", ") : "weniger als zwei Geräte online" },
    { id: "check-4", status: offlineSeen.length > 0 ? "passed" : "pending", evidence: offlineSeen.length ? `${offlineSeen.join(", ")} offline gemeldet` : "keine Gerät war zuvor online und ist jetzt offline" },
    { id: "check-5", status: completePairings.length > 0 ? "passed" : "pending", evidence: completePairings.length ? `${completePairings.length} vollständige Pairing(s) mit je zwei wechselseitigen Commands` : "kein vollständiges echtes Pairing mit genau zwei wechselseitigen Commands geladen" },
    { id: "check-6", status: confirmedPair && ackOkSeen ? "passed" : "pending", evidence: confirmedPair && ackOkSeen ? "wechselseitig bestätigt" : "keine wechselseitige Bestätigung" },
    { id: "check-7", status: channelMismatchSeen ? "passed" : "pending", evidence: channelMismatchSeen ? "409 wifi_channel_mismatch verarbeitet" : "kein 409 empfangen" },
    { id: "check-8", status: freshNavigationDevicesLoaded && devices.length > 0 ? "passed" : "pending", evidence: freshNavigationDevicesLoaded ? "Geräte beim frischen Seitenaufruf geladen" : "kein frischer Seitenaufruf mit Geräten" },
  ];
  const labels = new Map(CHECK_LABELS);
  return results.map((result) => ({ ...result, label: labels.get(result.id) || result.id }));
}
