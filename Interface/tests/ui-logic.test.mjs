import assert from "node:assert/strict";
import { test } from "node:test";

import {
  canPair,
  deviceHasPendingUnpair,
  eligibleForPairing,
  evaluateChecks,
  findConnectionConfirmed,
  pairingAckState,
} from "../ui-logic.js";

const baseDevice = (overrides = {}) => ({
  id: "A",
  online: true,
  wifi_channel: 1,
  peer_mac: "",
  peer_active: false,
  ...overrides,
});

test("eligibleForPairing requires online and known channel", () => {
  assert.equal(eligibleForPairing(baseDevice()), true);
  assert.equal(eligibleForPairing(baseDevice({ online: false })), false);
  assert.equal(eligibleForPairing(baseDevice({ wifi_channel: null })), false);
  assert.equal(eligibleForPairing(null), false);
});

test("canPair enforces same channel, distinct ids and online state", () => {
  const a = baseDevice();
  const b = baseDevice({ id: "B" });
  assert.equal(canPair(a, b), true);
  assert.equal(canPair(a, baseDevice({ id: "B", wifi_channel: 11 })), false);
  assert.equal(canPair(a, baseDevice({ id: "B", online: false })), false);
  assert.equal(canPair(a, a), false);
});

test("connection confirmed only with reciprocal online peer_active and matching peer_mac", () => {
  const a = baseDevice({ id: "AABBCCDDEE01", peer_mac: "AABBCCDDEE02", peer_active: true });
  const b = baseDevice({ id: "AABBCCDDEE02", peer_mac: "AABBCCDDEE01", peer_active: true });
  assert.deepEqual(findConnectionConfirmed([a, b]).map((device) => device.id).sort(), ["AABBCCDDEE01", "AABBCCDDEE02"]);

  assert.equal(findConnectionConfirmed([baseDevice({ id: "A" }), baseDevice({ id: "B" })]), null);
  assert.equal(findConnectionConfirmed([
    baseDevice({ id: "AABBCCDDEE01", peer_mac: "AABBCCDDEE02", peer_active: true, online: false }),
    baseDevice({ id: "AABBCCDDEE02", peer_mac: "AABBCCDDEE01", peer_active: true }),
  ]), null);
  assert.equal(findConnectionConfirmed([
    baseDevice({ id: "AABBCCDDEE01", peer_mac: "AABBCCDDEE02", peer_active: true }),
    baseDevice({ id: "AABBCCDDEE02", peer_mac: "AABBCCDDEE01", peer_active: false }),
  ]), null);
  assert.equal(findConnectionConfirmed([
    baseDevice({ id: "AABBCCDDEE01", peer_mac: "AABBCCDDEE02", peer_active: true }),
    baseDevice({ id: "AABBCCDDEE02", peer_mac: "AABBCCDDEE09", peer_active: true }),
  ]), null, "ack without reciprocal ping must not confirm");
});

test("pairingAckState summarizes two commands per pairing", () => {
  const pairingId = "pair_1";
  const command = (id, device) => ({ command_id: id, pairing_id: pairingId, device_id: device, peer_mac: "X", action: "pair", state: "pending" });
  assert.equal(pairingAckState([command("c1", "A"), command("c2", "B")], pairingId), "pending");
  assert.equal(pairingAckState([{ ...command("c1", "A"), state: "ack_ok" }, command("c2", "B")], pairingId), "pending");
  assert.equal(pairingAckState([{ ...command("c1", "A"), state: "ack_ok" }, { ...command("c2", "B"), state: "ack_ok" }], pairingId), "ack_ok");
  assert.equal(pairingAckState([{ ...command("c1", "A"), state: "ack_ok" }, { ...command("c2", "B"), state: "ack_failed" }], pairingId), "ack_failed");
  assert.equal(pairingAckState([command("c1", "A")], pairingId), null);
});

test("deviceHasPendingUnpair detects pending unpair only", () => {
  const command = (state) => ({ device_id: "A", action: "unpair", state });
  assert.equal(deviceHasPendingUnpair([command("pending")], "A"), true);
  assert.equal(deviceHasPendingUnpair([command("ack_ok")], "A"), false);
  assert.equal(deviceHasPendingUnpair([{ device_id: "B", action: "unpair", state: "pending" }], "A"), false);
  assert.equal(deviceHasPendingUnpair([{ device_id: "A", action: "pair", state: "pending" }], "A"), false);
});

const PAIRING = (pairingId, deviceId, peerMac, state) => ({
  command_id: `cmd_${pairingId}_${deviceId}`,
  pairing_id: pairingId,
  device_id: deviceId,
  peer_mac: peerMac,
  action: "pair",
  state,
});

test("evaluateChecks covers all eight checks", () => {
  const empty = evaluateChecks({
    devices: [],
    devicesOk: true,
    seenOnlineIds: [],
    channelMismatchSeen: false,
    freshNavigationDevicesLoaded: false,
    pairings: [],
  });
  assert.equal(empty.length, 8);
  assert.equal(empty[0].status, "passed");
  assert.ok(empty.every((check) => check.id && check.label));

  const aId = "AABBCCDDEE01";
  const bId = "AABBCCDDEE02";
  const devices = [
    baseDevice({ id: aId, wifi_channel: 6 }),
    baseDevice({ id: bId, wifi_channel: 6 }),
  ];
  const pairings = [PAIRING("pair_x", aId, bId, "ack_ok"), PAIRING("pair_x", bId, aId, "ack_ok")];
  const confirmed = evaluateChecks({
    devices: [
      { ...devices[0], peer_mac: bId, peer_active: true },
      { ...devices[1], peer_mac: aId, peer_active: true },
    ],
    devicesOk: true,
    seenOnlineIds: [aId],
    channelMismatchSeen: true,
    freshNavigationDevicesLoaded: true,
    pairings,
  });
  assert.deepEqual(
    Object.fromEntries(confirmed.map((check) => [check.id, check.status])),
    {
      "check-1": "pending",
      "check-2": "passed",
      "check-3": "passed",
      "check-4": "pending",
      "check-5": "passed",
      "check-6": "passed",
      "check-7": "passed",
      "check-8": "passed",
    },
    JSON.stringify(confirmed),
  );

  const oneCommandOnly = evaluateChecks({
    devices: [],
    devicesOk: true,
    seenOnlineIds: [],
    channelMismatchSeen: false,
    freshNavigationDevicesLoaded: false,
    pairings: [PAIRING("pair_incomplete", aId, bId, "pending")],
  });
  assert.equal(oneCommandOnly.find((check) => check.id === "check-5").status, "pending");

  const wrongPeer = evaluateChecks({
    devices: [],
    devicesOk: true,
    seenOnlineIds: [],
    channelMismatchSeen: false,
    freshNavigationDevicesLoaded: false,
    pairings: [
      PAIRING("pair_wrong", aId, bId, "pending"),
      PAIRING("pair_wrong", bId, aId, "pending"),
      PAIRING("pair_wrong", "AABBCCDDEE03", aId, "pending"),
    ],
  });
  assert.equal(wrongPeer.find((check) => check.id === "check-5").status, "pending");
});

test("check 4 passes when a previously online device reports offline", () => {
  const aId = "AABBCCDDEE01";
  const result = evaluateChecks({
    devices: [baseDevice({ id: aId, online: false })],
    devicesOk: true,
    seenOnlineIds: [aId],
    channelMismatchSeen: false,
    freshNavigationDevicesLoaded: false,
    pairings: [],
  });
  const check4 = result.find((check) => check.id === "check-4");
  assert.equal(check4.status, "passed");
  assert.ok(check4.evidence.includes(aId));
});

test("check 6 not passed without reciprocal confirmation", () => {
  const aId = "AABBCCDDEE01";
  const bId = "AABBCCDDEE02";
  const pairings = [PAIRING("pair_x", aId, bId, "ack_ok"), PAIRING("pair_x", bId, aId, "ack_ok")];
  const result = evaluateChecks({
    devices: [
      baseDevice({ id: aId, peer_mac: bId, peer_active: true }),
      baseDevice({ id: bId, peer_mac: aId, peer_active: false }),
    ],
    devicesOk: true,
    seenOnlineIds: [],
    channelMismatchSeen: false,
    freshNavigationDevicesLoaded: false,
    pairings,
  });
  assert.equal(result.find((check) => check.id === "check-6").status, "pending");
});
