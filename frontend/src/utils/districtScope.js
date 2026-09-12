// 戰情室行政區限縮：清單、篩選、區界／站點包絡。區界來自公開鄉鎮圖資，非正式即時地政。

export const CITY_SCOPE = "全市";
export const CITY_LABEL = "新北市全區";

export function isCityScope(district) {
  return !district || district === CITY_SCOPE;
}

export function listDistricts(stations) {
  return [...new Set((stations ?? []).map((row) => row?.district).filter(Boolean))].sort((a, b) =>
    a.localeCompare(b, "zh-Hant"),
  );
}

export function filterByDistrict(items, district) {
  if (isCityScope(district)) return items ?? [];
  return (items ?? []).filter((row) => row?.district === district);
}

export function convexHull(points) {
  const uniq = [];
  const seen = new Set();
  for (const point of points ?? []) {
    const lng = Number(point?.[0]);
    const lat = Number(point?.[1]);
    if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
    const key = `${lng}:${lat}`;
    if (seen.has(key)) continue;
    seen.add(key);
    uniq.push([lng, lat]);
  }
  if (uniq.length < 3) return uniq;
  const sorted = uniq.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const cross = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower = [];
  for (const point of sorted) {
    while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], point) <= 0) {
      lower.pop();
    }
    lower.push(point);
  }
  const upper = [];
  for (const point of sorted.slice().reverse()) {
    while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], point) <= 0) {
      upper.pop();
    }
    upper.push(point);
  }
  lower.pop();
  upper.pop();
  return [...lower, ...upper];
}

export function closeRing(ring) {
  if (!ring?.length) return [];
  const first = ring[0];
  const last = ring[ring.length - 1];
  if (first[0] === last[0] && first[1] === last[1]) return ring;
  return [...ring, first];
}

export function padRing(ring, padDeg = 0.004) {
  const closed = closeRing(ring);
  if (closed.length < 3) return closed;
  const body = closed[0][0] === closed[closed.length - 1][0] && closed[0][1] === closed[closed.length - 1][1]
    ? closed.slice(0, -1)
    : closed;
  const cx = body.reduce((sum, point) => sum + point[0], 0) / body.length;
  const cy = body.reduce((sum, point) => sum + point[1], 0) / body.length;
  return closeRing(
    body.map(([lng, lat]) => {
      const dx = lng - cx;
      const dy = lat - cy;
      const dist = Math.hypot(dx, dy) || 1;
      return [lng + (dx / dist) * padDeg, lat + (dy / dist) * padDeg];
    }),
  );
}

export function stationHull(stations, padDeg = 0.004) {
  const points = (stations ?? [])
    .filter((row) => Number.isFinite(Number(row?.lng)) && Number.isFinite(Number(row?.lat)))
    .map((row) => [Number(row.lng), Number(row.lat)]);
  const hull = convexHull(points);
  if (hull.length < 3) return null;
  return [padRing(hull, padDeg)];
}

export function districtOutline(district, stations = [], catalog = {}) {
  if (isCityScope(district)) return null;
  const polygons = catalog?.[district];
  if (polygons?.length) {
    return { district, polygons, source: "town-boundary" };
  }
  const hull = stationHull(stations);
  if (!hull) return null;
  return { district, polygons: [hull], source: "station-hull" };
}

export function outlineBounds(polygons) {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  for (const polygon of polygons ?? []) {
    const rings = Array.isArray(polygon[0]?.[0]) ? polygon : [polygon];
    for (const ring of rings) {
      for (const point of ring) {
        const lng = Number(point?.[0]);
        const lat = Number(point?.[1]);
        if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
        minLng = Math.min(minLng, lng);
        minLat = Math.min(minLat, lat);
        maxLng = Math.max(maxLng, lng);
        maxLat = Math.max(maxLat, lat);
      }
    }
  }
  if (!Number.isFinite(minLng)) return null;
  return [
    [minLng, minLat],
    [maxLng, maxLat],
  ];
}

export function countScopedCoverage({
  stations,
  mode,
  historyFrame,
  temporalStations,
  recommendations,
}) {
  const total = stations?.length ?? 0;
  if (mode === "live") {
    return { covered: total, available: total };
  }
  const ids = new Set();
  if (mode === "past") {
    for (const row of historyFrame?.stations ?? []) {
      if (row?.station_id != null) ids.add(row.station_id);
    }
  }
  if (mode === "predict") {
    for (const row of recommendations ?? []) {
      const byHorizon = row?.arrival_by_horizon;
      const bikes = Number.isFinite(Number(row?.predicted_at_arrival))
        || (byHorizon && Object.values(byHorizon).some((value) => Number.isFinite(Number(value))));
      if (row?.station_id && bikes) ids.add(row.station_id);
    }
  }
  if (!ids.size) {
    for (const row of temporalStations ?? []) {
      if (row?.stationId != null) ids.add(row.stationId);
    }
  }
  const covered = (stations ?? []).filter((row) => ids.has(row.station_id)).length;
  return { covered, available: ids.size || covered };
}
