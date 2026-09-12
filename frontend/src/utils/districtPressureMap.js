/** 把新北 29 區界投影成 SVG path，給服務水準看板用。圖資非正式即時地政。 */

import catalog from "../data/newtaipeiDistricts.json" with { type: "json" };

export const DISTRICT_MAP_VIEW = { w: 360, h: 430, pad: 8 };

function walkRings(multi, visit) {
  for (const polygon of multi ?? []) {
    const rings = Array.isArray(polygon[0]?.[0]) ? polygon : [polygon];
    for (const ring of rings) visit(ring);
  }
}

function catalogBounds(polygons) {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  for (const multi of Object.values(polygons ?? {})) {
    walkRings(multi, (ring) => {
      for (const point of ring) {
        const lng = Number(point?.[0]);
        const lat = Number(point?.[1]);
        if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
        minLng = Math.min(minLng, lng);
        minLat = Math.min(minLat, lat);
        maxLng = Math.max(maxLng, lng);
        maxLat = Math.max(maxLat, lat);
      }
    });
  }
  return { minLng, minLat, maxLng, maxLat };
}

function project(lng, lat, bounds, view) {
  const xSpan = bounds.maxLng - bounds.minLng || 1;
  const ySpan = bounds.maxLat - bounds.minLat || 1;
  const innerW = view.w - view.pad * 2;
  const innerH = view.h - view.pad * 2;
  const scale = Math.min(innerW / xSpan, innerH / ySpan);
  const usedW = xSpan * scale;
  const usedH = ySpan * scale;
  const ox = view.pad + (innerW - usedW) / 2;
  const oy = view.pad + (innerH - usedH) / 2;
  return [
    ox + (lng - bounds.minLng) * scale,
    oy + (bounds.maxLat - lat) * scale,
  ];
}

function ringsToPath(multi, bounds, view) {
  const parts = [];
  walkRings(multi, (ring) => {
    if (!ring?.length) return;
    const cmds = ring.map((point, index) => {
      const [x, y] = project(Number(point[0]), Number(point[1]), bounds, view);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
    });
    parts.push(`${cmds.join(" ")} Z`);
  });
  return parts.join(" ");
}

const BOUNDS = catalogBounds(catalog.polygons);

export const DISTRICT_SHAPES = Object.entries(catalog.polygons ?? {}).map(([district, multi]) => ({
  district,
  d: ringsToPath(multi, BOUNDS, DISTRICT_MAP_VIEW),
}));
