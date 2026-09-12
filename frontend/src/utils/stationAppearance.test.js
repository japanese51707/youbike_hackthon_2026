import test from "node:test";
import assert from "node:assert/strict";
import { getRentalStatus, hasAvailableElectricBike } from "./stationAppearance.js";
import { getStationPinIcon } from "./stationPinIcon.js";

test("official rental status does not relabel low/high operational water levels", () => {
  for (const status of ["low", "normal", "high"]) {
    const station = { status };
    assert.equal(getRentalStatus(station), "normal");
    assert.equal(station.status, status);
  }
  assert.equal(getRentalStatus({ status: "empty" }), "empty");
  assert.equal(getRentalStatus({ status: "full" }), "full");
  assert.equal(getRentalStatus({ status: "full", service_available: false }), "offline");
  assert.equal(getRentalStatus({ status: "unexpected" }), "unknown");
});
test("electric badge requires positive available count, never infers from ordinary bike count", () => {
  for (const available_electric_bikes of [undefined, null, 0, -1, "3", Infinity, NaN]) {
    assert.equal(hasAvailableElectricBike({ status: "normal", available_electric_bikes, available_bikes: 20 }), false);
  }
  assert.equal(hasAvailableElectricBike({ status: "normal", available_electric_bikes: 2 }), true);
  assert.equal(hasAvailableElectricBike({ status: "offline", available_electric_bikes: 2 }), false);
  assert.equal(hasAvailableElectricBike({ status: "empty", available_electric_bikes: 2 }), false);
});
test("icons are bounded, cached, correctly anchored and reject color injection", () => {
  assert.equal(getStationPinIcon(.5, "#87ce24"), getStationPinIcon(.51, "#87ce24"));
  assert.notEqual(getStationPinIcon(.5, "#87ce24"), getStationPinIcon(.5, "#87ce24", true));
  const icon = getStationPinIcon(NaN, '<script>');
  const svg = decodeURIComponent(icon.url.split(',')[1]);
  assert.equal(icon.anchorY, 75);
  assert.ok(svg.includes('#858783'));
  assert.ok(!svg.includes('<script>'));
});
