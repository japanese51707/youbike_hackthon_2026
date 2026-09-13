/** 把新北 29 區界投影成 SVG path，給服務水準看板用。圖資非正式即時地政。 */

import catalog from "../data/newtaipeiDistricts.json" with { type: "json" };

export const DISTRICT_MAP_VIEW = { w: 360, h: 430, pad: 8 };
export const DISTRICT_MAP_FIT = { x: 0, y: 0, w: DISTRICT_MAP_VIEW.w, h: DISTRICT_MAP_VIEW.h };
export const DISTRICT_MAP_MIN_ZOOM = 1;
export const DISTRICT_MAP_MAX_ZOOM = 6;
export const DISTRICT_FIT_MAX_ZOOM = 14;

export function isFitView(view, fit = DISTRICT_MAP_FIT, epsilon = 0.4) {
  return (
    Math.abs(view.x - fit.x) < epsilon
    && Math.abs(view.y - fit.y) < epsilon
    && Math.abs(view.w - fit.w) < epsilon
    && Math.abs(view.h - fit.h) < epsilon
  );
}

export function clampMapView(view, fit = DISTRICT_MAP_FIT, maxZoom = DISTRICT_MAP_MAX_ZOOM) {
  const nextW = Math.min(fit.w, Math.max(fit.w / maxZoom, view.w));
  const nextH = nextW * (fit.h / fit.w);
  const maxX = fit.x + fit.w - nextW;
  const maxY = fit.y + fit.h - nextH;
  return {
    x: Math.min(Math.max(fit.x, view.x), Math.max(fit.x, maxX)),
    y: Math.min(Math.max(fit.y, view.y), Math.max(fit.y, maxY)),
    w: nextW,
    h: nextH,
  };
}

/** 對準視窗內一點縮放。factor > 1 拉遠，< 1 拉近。 */
export function zoomMapView(view, { x, y, factor }, fit = DISTRICT_MAP_FIT) {
  const nextW = view.w * factor;
  const nextH = view.h * factor;
  return clampMapView({
    x: x - (x - view.x) * (nextW / view.w),
    y: y - (y - view.y) * (nextH / view.h),
    w: nextW,
    h: nextH,
  }, fit);
}

export function panMapView(view, { dx, dy }, fit = DISTRICT_MAP_FIT) {
  return clampMapView({ ...view, x: view.x + dx, y: view.y + dy }, fit);
}

export function easeInOutCubic(t) {
  const x = Math.min(1, Math.max(0, t));
  return x < 0.5 ? 4 * x * x * x : 1 - ((-2 * x + 2) ** 3) / 2;
}

export function lerpMapView(from, to, t) {
  const k = easeInOutCubic(t);
  return {
    x: from.x + (to.x - from.x) * k,
    y: from.y + (to.y - from.y) * k,
    w: from.w + (to.w - from.w) * k,
    h: from.h + (to.h - from.h) * k,
  };
}

/** 讓 viewBox 剛好包住該區，比例維持全市畫布。 */
export function viewForBBox(bbox, fit = DISTRICT_MAP_FIT, pad = 14, maxZoom = DISTRICT_FIT_MAX_ZOOM) {
  const bw = Math.max((bbox.maxX - bbox.minX) || 8, 8) + pad * 2;
  const bh = Math.max((bbox.maxY - bbox.minY) || 8, 8) + pad * 2;
  const aspect = fit.w / fit.h;
  const w = bw / bh > aspect ? bw : bh * aspect;
  const h = w / aspect;
  return clampMapView({
    x: (bbox.minX + bbox.maxX) / 2 - w / 2,
    y: (bbox.minY + bbox.maxY) / 2 - h / 2,
    w,
    h,
  }, fit, maxZoom);
}

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

function ringsToBBox(multi, bounds, view) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  walkRings(multi, (ring) => {
    for (const point of ring ?? []) {
      const [x, y] = project(Number(point[0]), Number(point[1]), bounds, view);
      if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  });
  return { minX, minY, maxX, maxY };
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
  bbox: ringsToBBox(multi, BOUNDS, DISTRICT_MAP_VIEW),
}));

export function viewForDistrict(district, fit = DISTRICT_MAP_FIT) {
  const shape = DISTRICT_SHAPES.find((row) => row.district === district);
  return shape?.bbox ? viewForBBox(shape.bbox, fit) : { ...fit };
}
