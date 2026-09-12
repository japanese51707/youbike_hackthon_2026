import test from "node:test";
import assert from "node:assert/strict";
import { palettes, resolveAppearance, validAppearance } from "./palettes.js";
import { createBasemapStyle } from "../config/darkBasemapStyle.js";
import { createNoBasemapStyle } from "../config/noBasemapStyle.js";
import { applyMapAppearance } from "../components/map/applyMapAppearance.js";

function luminance(hex) {
  return hex.slice(1).match(/../g).map(v => parseInt(v, 16) / 255)
    .map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
    .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
}
function contrast(a, b) {
  const [x, y] = [luminance(a), luminance(b)].sort((a, b) => b - a);
  return (x + .05) / (y + .05);
}
test("explicit appearance overrides system; corrupt preferences follow system", () => {
  assert.equal(resolveAppearance("light", true), "light");
  assert.equal(resolveAppearance("dark", false), "dark");
  assert.equal(resolveAppearance("system", true), "dark");
  assert.equal(resolveAppearance("system", false), "light");
  assert.equal(validAppearance("unexpected"), "system");
  assert.equal(validAppearance(null), "system");
});
test("both modes keep normal and secondary text readable on every surface", () => {
  for (const [mode, p] of Object.entries(palettes)) {
    for (const surface of [p.bg, p.bgSoft, p.panel, p.panel2]) {
      for (const text of [p.text, p.muted, p.primary]) {
        assert.ok(contrast(text, surface) >= 4.5, `${mode} ${text} on ${surface}: ${contrast(text, surface)}`);
      }
    }
    assert.ok(contrast(p.onAccent, p.accent) >= 4.5);
  }
});
test("day/night retain identical map sources, layer identities and offline boundaries", () => {
  const day = createBasemapStyle("light");
  const night = createBasemapStyle("dark");
  assert.deepEqual(day.sources, night.sources);
  assert.equal(day.glyphs, night.glyphs);
  assert.equal(day.sprite, night.sprite);
  assert.deepEqual(day.layers.map(l => l.id), night.layers.map(l => l.id));
  assert.notEqual(day.layers[0].paint["background-color"], night.layers[0].paint["background-color"]);
  assert.deepEqual(createNoBasemapStyle("dark").sources, {});
});
test("appearance updates only paint properties, preserving the map and data overlay", () => {
  const changes = [];
  const map = { getLayer: () => true, setPaintProperty: (...args) => changes.push(args) };
  applyMapAppearance(map, "dark", false);
  assert.ok(changes.length > 5);
  assert.ok(changes.every(([, property]) => property.endsWith("color")));
  changes.length = 0;
  applyMapAppearance(map, "light", true);
  assert.deepEqual(changes, [["no-basemap-background", "background-color", palettes.light.map.background]]);
});
