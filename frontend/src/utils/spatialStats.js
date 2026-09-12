// 空間／網路統計（戰情室分析用）。
// 全部為純函式、確定性、來自既有站點資料，不呼叫外部服務。
// Gi*／中心性在站數很少時不具可靠推論；洞察層會依樣本數改標誠實度。

import { mean, standardDeviation } from "simple-statistics";
import { haversineKm } from "./geo.js";

const KM_PER_DEG_LAT = 111.32;

export function hasFiniteCoords(station) {
  return Number.isFinite(Number(station?.lat)) && Number.isFinite(Number(station?.lng));
}

export function stationsWithCoords(stations) {
  return (stations ?? []).filter(hasFiniteCoords);
}

// 站點的「壓力值」：越缺車或越滿都算壓力；用使用率偏離 50% 的程度 + 空/滿加權。
export function stationPressure(station) {
  const usage = Number(station.usage_rate);
  const base = Number.isFinite(usage) ? Math.abs(usage - 50) / 50 : 0;
  const extreme = station.status === "empty" || station.status === "full" ? 0.3 : 0;
  return Math.min(1, base + extreme);
}

function cellKey(lat, lng, cellDeg) {
  return `${Math.floor(lat / cellDeg)}:${Math.floor(lng / cellDeg)}`;
}

// 等距格網索引：查詢時多取一圈，再用精準距離過濾。
export function buildSpatialIndex(stations, cellKm = 3) {
  const pts = stationsWithCoords(stations);
  const cellDeg = cellKm / KM_PER_DEG_LAT;
  const cells = new Map();
  pts.forEach((station, index) => {
    const key = cellKey(Number(station.lat), Number(station.lng), cellDeg);
    const bucket = cells.get(key);
    if (bucket) bucket.push(index);
    else cells.set(key, [index]);
  });
  return { stations: pts, cells, cellDeg };
}

export function queryNearbyIndices(index, lat, lng, radiusKm) {
  const { stations, cells, cellDeg } = index;
  const radiusDeg = (radiusKm / KM_PER_DEG_LAT) * 1.2;
  const minI = Math.floor((lat - radiusDeg) / cellDeg);
  const maxI = Math.floor((lat + radiusDeg) / cellDeg);
  const minJ = Math.floor((lng - radiusDeg) / cellDeg);
  const maxJ = Math.floor((lng + radiusDeg) / cellDeg);
  const hits = [];
  for (let i = minI; i <= maxI; i += 1) {
    for (let j = minJ; j <= maxJ; j += 1) {
      const bucket = cells.get(`${i}:${j}`);
      if (!bucket) continue;
      for (const idx of bucket) {
        const station = stations[idx];
        if (haversineKm({ lat, lng }, station) <= radiusKm) hits.push(idx);
      }
    }
  }
  return hits;
}

function kNearest(index, stationIndex, k) {
  const origin = index.stations[stationIndex];
  let radius = 1.5;
  let found = [];
  for (let step = 0; step < 8; step += 1) {
    found = queryNearbyIndices(index, Number(origin.lat), Number(origin.lng), radius)
      .filter((idx) => idx !== stationIndex);
    if (found.length >= k) break;
    radius *= 2;
  }
  return found
    .map((idx) => ({
      idx,
      km: haversineKm(origin, index.stations[idx]),
    }))
    .sort((a, b) => a.km - b.km)
    .slice(0, k);
}

export function nearestStationKm(index, lat, lng, capKm = 4) {
  let radius = 0.8;
  while (radius <= capKm) {
    const hits = queryNearbyIndices(index, lat, lng, radius);
    if (hits.length) {
      let best = Infinity;
      for (const idx of hits) {
        const distance = haversineKm({ lat, lng }, index.stations[idx]);
        if (distance < best) best = distance;
      }
      return Math.min(best, capKm);
    }
    radius *= 2;
  }
  return capKm;
}

// Getis-Ord Gi*（標準化 z 分數）：某站與其鄰近的壓力是否形成顯著高/低值群聚。
export function getisOrdGiStar(stations, { radiusKm = 3 } = {}) {
  const index = buildSpatialIndex(stations, radiusKm);
  const pts = index.stations;
  const n = pts.length;
  if (n < 3) {
    return pts.map((station) => ({ station, z: 0, pressure: stationPressure(station) }));
  }
  const values = pts.map(stationPressure);
  const m = mean(values);
  const sd = standardDeviation(values) || 1e-9;

  return pts.map((station, i) => {
    const neighbors = queryNearbyIndices(index, Number(station.lat), Number(station.lng), radiusKm);
    const sumW = neighbors.length;
    const sumWX = neighbors.reduce((acc, idx) => acc + values[idx], 0);
    const numerator = sumWX - m * sumW;
    const denominator = sd * Math.sqrt((n * sumW - sumW * sumW) / (n - 1)) || 1e-9;
    return { station, z: numerator / denominator, pressure: values[i] };
  });
}

export function giStarClass(z) {
  if (z >= 2.58) return { key: "hot99", label: "顯著熱點 99%", color: [201, 42, 42] };
  if (z >= 1.96) return { key: "hot95", label: "熱點 95%", color: [255, 107, 107] };
  if (z <= -2.58) return { key: "cold99", label: "顯著冷點 99%", color: [25, 113, 194] };
  if (z <= -1.96) return { key: "cold95", label: "冷點 95%", color: [77, 171, 247] };
  return { key: "ns", label: "不顯著", color: [90, 100, 120] };
}

export function buildKnnNetwork(stations, { k = 3 } = {}) {
  const index = buildSpatialIndex(stations, 2);
  const pts = index.stations;
  const edgeSet = new Map();
  const edges = [];
  pts.forEach((_, i) => {
    for (const { idx, km } of kNearest(index, i, k)) {
      const id = i < idx ? `${i}-${idx}` : `${idx}-${i}`;
      if (edgeSet.has(id)) continue;
      edgeSet.set(id, true);
      edges.push({ from: pts[i], to: pts[idx], km });
    }
  });
  return edges;
}

export function degreeCentrality(stations, edges) {
  const score = new Map(stations.map((s) => [s.station_id, 0]));
  for (const edge of edges) {
    const weight = 1 / (1 + edge.km);
    score.set(edge.from.station_id, (score.get(edge.from.station_id) || 0) + weight);
    score.set(edge.to.station_id, (score.get(edge.to.station_id) || 0) + weight);
  }
  const values = [...score.values()];
  const max = Math.max(1e-9, ...values);
  const normalized = new Map();
  for (const [id, value] of score) normalized.set(id, value / max);
  return normalized;
}
