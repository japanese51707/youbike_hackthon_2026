// 空間/網路統計（戰情室分析用）。
// 重要：目前 mock 站數少，這些統計僅「方法展示」，非可靠推論；真實資料進來才有統計意義。
// 全部為純函式、確定性、來自既有站點資料，不呼叫外部服務。

import { mean, standardDeviation } from "simple-statistics";
import { haversineKm } from "./geo.js";

// 站點的「壓力值」：越缺車或越滿都算壓力；用使用率偏離 50% 的程度 + 空/滿加權。
export function stationPressure(station) {
  const usage = Number(station.usage_rate);
  const base = Number.isFinite(usage) ? Math.abs(usage - 50) / 50 : 0; // 0~1
  const extreme = station.status === "empty" || station.status === "full" ? 0.3 : 0;
  return Math.min(1, base + extreme);
}

// Getis-Ord Gi*（標準化 z 分數）：某站與其鄰近的壓力是否形成顯著高/低值群聚。
// 使用距離門檻的二元空間權重（含自身）。回傳每站 { station, z, pressure }。
export function getisOrdGiStar(stations, { radiusKm = 3 } = {}) {
  const n = stations.length;
  if (n < 3) {
    return stations.map((s) => ({ station: s, z: 0, pressure: stationPressure(s) }));
  }
  const values = stations.map(stationPressure);
  const m = mean(values);
  const sd = standardDeviation(values) || 1e-9;

  return stations.map((s, i) => {
    let sumW = 0;
    let sumWX = 0;
    for (let j = 0; j < n; j += 1) {
      const w =
        i === j
          ? 1
          : haversineKm(
              { lat: s.lat, lng: s.lng },
              { lat: stations[j].lat, lng: stations[j].lng },
            ) <= radiusKm
            ? 1
            : 0;
      sumW += w;
      sumWX += w * values[j];
    }
    // Gi* z 分數公式
    const numerator = sumWX - m * sumW;
    const denominator =
      sd * Math.sqrt((n * sumW - sumW * sumW) / (n - 1)) || 1e-9;
    const z = numerator / denominator;
    return { station: s, z, pressure: values[i] };
  });
}

// 把 Gi* z 分數映射為熱點類別（顯著性門檻約 ±1.96 / ±2.58）
export function giStarClass(z) {
  if (z >= 2.58) return { key: "hot99", label: "顯著熱點 99%", color: [201, 42, 42] };
  if (z >= 1.96) return { key: "hot95", label: "熱點 95%", color: [255, 107, 107] };
  if (z <= -2.58) return { key: "cold99", label: "顯著冷點 99%", color: [25, 113, 194] };
  if (z <= -1.96) return { key: "cold95", label: "冷點 95%", color: [77, 171, 247] };
  return { key: "ns", label: "不顯著", color: [90, 100, 120] };
}

// 建 k-近鄰網路：每站連到最近的 k 個站（去重無向邊）。
export function buildKnnNetwork(stations, { k = 3 } = {}) {
  const edgeSet = new Map();
  const edges = [];
  stations.forEach((s, i) => {
    const dists = stations
      .map((t, j) => ({
        j,
        km: i === j ? Infinity : haversineKm({ lat: s.lat, lng: s.lng }, { lat: t.lat, lng: t.lng }),
      }))
      .sort((a, b) => a.km - b.km)
      .slice(0, k);
    for (const { j, km } of dists) {
      const id = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (!edgeSet.has(id)) {
        edgeSet.set(id, true);
        edges.push({ from: stations[i], to: stations[j], km });
      }
    }
  });
  return edges;
}

// 度中心性（含距離衰減的加權）：連結越多、越近，中心性越高。回傳 Map(station_id -> 0~1)。
export function degreeCentrality(stations, edges) {
  const score = new Map(stations.map((s) => [s.station_id, 0]));
  for (const e of edges) {
    const w = 1 / (1 + e.km); // 距離衰減
    score.set(e.from.station_id, score.get(e.from.station_id) + w);
    score.set(e.to.station_id, score.get(e.to.station_id) + w);
  }
  const values = [...score.values()];
  const max = Math.max(1e-9, ...values);
  const normalized = new Map();
  for (const [id, v] of score) normalized.set(id, v / max);
  return normalized;
}
