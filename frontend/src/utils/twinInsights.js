// 戰情室洞察引擎：把站況快照收成可核對的指標與模板結論。
// 只做規劃解讀，不產出派工指令（守 ADR-004）。缺資料就拒絕下結論，不插補。

import { ANALYSIS_CATALOG } from "../config/analysisCatalog.js";
import {
  buildKnnNetwork,
  buildSpatialIndex,
  degreeCentrality,
  getisOrdGiStar,
  giStarClass,
  nearestStationKm,
  queryNearbyIndices,
  stationPressure,
  stationsWithCoords,
} from "./spatialStats.js";
import { flowPairStats, pairDispatchFlows } from "./twinFlow.js";
import { emptyRate } from "./twinSnapshot.js";

export const TWIN_INSIGHT = {
  giRadiusKm: 3,
  giRealMinStations: 50,
  highPressure: 0.5,
  gapThresholdKm: 0.8,
  coverageCapKm: 4,
  coverageSteps: 26,
  coveragePadDeg: 0.04,
  districtMinStations: 5,
  topN: 3,
  cityWideCoverage: 0.8,
};

const CATALOG_BY_KEY = new Map(ANALYSIS_CATALOG.map((item) => [item.key, item]));

function round(value, digits = 1) {
  const factor = 10 ** digits;
  return Math.round(Number(value) * factor) / factor;
}

function pct(part, total, digits = 1) {
  if (!total) return 0;
  return round((part / total) * 100, digits);
}

function listNames(items) {
  return items.join("、");
}

function catalogOf(key) {
  return CATALOG_BY_KEY.get(key) ?? { key, name: key, dataMode: "method" };
}

function emptyLayer(key, extra = {}) {
  const item = catalogOf(key);
  return {
    key,
    title: item.name,
    dataMode: extra.dataMode ?? item.dataMode,
    metrics: extra.metrics ?? [],
    findings: extra.findings ?? [],
    evidence: extra.evidence ?? [],
    caveats: extra.caveats ?? [],
  };
}

function blockedLayer(key, reason, extra = {}) {
  return emptyLayer(key, {
    ...extra,
    findings: [],
    caveats: [reason, ...(extra.caveats ?? [])],
  });
}

export function pickObservedAt(stations) {
  const row = (stations ?? []).find((s) => s?.observed_at || s?.source_timestamp || s?.timestamp);
  return row?.observed_at || row?.source_timestamp || row?.timestamp || null;
}

function groupByDistrict(stations) {
  const groups = new Map();
  for (const station of stations) {
    const district = station.district || "未分區";
    const list = groups.get(district);
    if (list) list.push(station);
    else groups.set(district, [station]);
  }
  return groups;
}

function topDistricts(rows, take = TWIN_INSIGHT.topN) {
  return rows.slice(0, take).map((row) => row.district);
}

export function districtStatusRows(stations, { minStations = TWIN_INSIGHT.districtMinStations } = {}) {
  return [...groupByDistrict(stations).entries()]
    .map(([district, list]) => {
      const empty = list.filter((s) => s.status === "empty").length;
      return {
        district,
        count: list.length,
        empty,
        emptyRate: pct(empty, list.length),
      };
    })
    .filter((row) => row.count >= minStations)
    .sort((a, b) => b.emptyRate - a.emptyRate || b.empty - a.empty);
}

export function buildGaugeInsight(stations) {
  const n = stations.length;
  const empty = stations.filter((s) => s.status === "empty").length;
  const full = stations.filter((s) => s.status === "full").length;
  const low = stations.filter((s) => s.status === "low").length;
  const high = stations.filter((s) => s.status === "high").length;
  const emptyRate = pct(empty, n);
  const fullRate = pct(full, n);
  const ranked = districtStatusRows(stations);
  const worst = ranked[0];
  const findings = [
    `全市 ${n} 站中，空站 ${empty}（${emptyRate}%）、滿站 ${full}（${fullRate}%）。`,
  ];
  if (worst && worst.emptyRate > emptyRate) {
    findings.push(
      `空站最集中在${worst.district}（該區 ${worst.empty}/${worst.count}，${worst.emptyRate}%，高於全市）。`,
    );
  }
  return {
    ...emptyLayer("gauge", { dataMode: "real" }),
    metrics: [
      { label: "空站率", value: emptyRate, unit: "%" },
      { label: "滿站率", value: fullRate, unit: "%" },
      { label: "偏低／偏高", value: `${low}／${high}`, unit: "站" },
    ],
    findings,
    evidence: ranked.slice(0, TWIN_INSIGHT.topN).map((row) => ({
      district: row.district,
      label: row.district,
      detail: `空站 ${row.empty}/${row.count}（${row.emptyRate}%）`,
    })),
    caveats: ["狀態來自當前快照的可借／可還，不是預測區間。"],
  };
}

export function buildKdeInsight(stations) {
  const pressures = stations.map((s) => ({ station: s, pressure: stationPressure(s) }));
  const total = pressures.reduce((acc, row) => acc + row.pressure, 0);
  const high = pressures.filter((row) => row.pressure >= TWIN_INSIGHT.highPressure);
  const byDistrict = [...groupByDistrict(stations).entries()]
    .map(([district, list]) => {
      const sum = list.reduce((acc, s) => acc + stationPressure(s), 0);
      return { district, sum, count: list.length, share: pct(sum, total) };
    })
    .sort((a, b) => b.sum - a.sum);
  const leaders = byDistrict.filter((row) => row.share > 0).slice(0, TWIN_INSIGHT.topN);
  const findings = [
    `壓力偏高站 ${high.length} 座（使用率明顯偏離 50% 或已空／滿）。`,
  ];
  if (leaders.length) {
    findings.push(`壓力加總前段在${listNames(leaders.map((row) => row.district))}，合計約佔全市 ${leaders.reduce((acc, row) => acc + row.share, 0)}%。`);
  }
  return {
    ...emptyLayer("kde", { dataMode: "real" }),
    metrics: [
      { label: "平均壓力", value: round(total / Math.max(stations.length, 1), 2), unit: "" },
      { label: "偏高站", value: high.length, unit: "站" },
    ],
    findings,
    evidence: high
      .sort((a, b) => b.pressure - a.pressure)
      .slice(0, 5)
      .map((row) => ({
        station_id: row.station.station_id,
        label: row.station.station_name,
        district: row.station.district,
        detail: `壓力 ${round(row.pressure, 2)}`,
      })),
    caveats: ["壓力由使用率偏離 50% 與空／滿狀態算出，不是真實人流。"],
  };
}

export function buildVoronoiInsight(stations) {
  const dataMode = stations.length >= TWIN_INSIGHT.giRealMinStations ? "real" : "method";
  if (stations.length < 3) {
    return emptyLayer("voronoi", {
      dataMode: "method",
      caveats: ["站點少於 3，無法計算 Gi*。"],
    });
  }
  const gi = getisOrdGiStar(stations, { radiusKm: TWIN_INSIGHT.giRadiusKm });
  const classified = gi.map((row) => ({ ...row, cls: giStarClass(row.z) }));
  const hot = classified.filter((row) => row.cls.key.startsWith("hot"));
  const cold = classified.filter((row) => row.cls.key.startsWith("cold"));
  const hotDistricts = [...groupByDistrict(hot.map((row) => row.station)).entries()]
    .map(([district, list]) => ({ district, count: list.length }))
    .sort((a, b) => b.count - a.count);
  const findings = [
    `在 ${TWIN_INSIGHT.giRadiusKm} km 鄰域下，顯著熱點 ${hot.length} 站、冷點 ${cold.length} 站。`,
  ];
  if (hotDistricts.length) {
    findings.push(`熱點主要在${listNames(topDistricts(hotDistricts))}。`);
  } else {
    findings.push("目前沒有達 95% 顯著的壓力熱點。");
  }
  return {
    ...emptyLayer("voronoi", { dataMode }),
    metrics: [
      { label: "熱點", value: hot.length, unit: "站" },
      { label: "冷點", value: cold.length, unit: "站" },
    ],
    findings,
    evidence: hot
      .sort((a, b) => b.z - a.z)
      .slice(0, 5)
      .map((row) => ({
        station_id: row.station.station_id,
        label: row.station.station_name,
        district: row.station.district,
        detail: `${row.cls.label}　z=${round(row.z, 2)}`,
      })),
    caveats: [
      dataMode === "method"
        ? `站數 ${stations.length} < ${TWIN_INSIGHT.giRealMinStations}，Gi* 僅方法展示。`
        : `鄰域 ${TWIN_INSIGHT.giRadiusKm} km、壓力定義見熱力圖；顯著性門檻約 ±1.96／±2.58。`,
    ],
  };
}

export function buildDensityInsight(stations) {
  const docks = stations.map((s) => Number(s.total_docks) || 0);
  const totalDocks = docks.reduce((acc, value) => acc + value, 0);
  const median = docks.slice().sort((a, b) => a - b)[Math.floor(docks.length / 2)] || 0;
  const cityMeanPressure = stations.reduce((acc, s) => acc + stationPressure(s), 0) / Math.max(stations.length, 1);
  const rows = [...groupByDistrict(stations).entries()]
    .map(([district, list]) => {
      const capacity = list.reduce((acc, s) => acc + (Number(s.total_docks) || 0), 0);
      const pressure = list.reduce((acc, s) => acc + stationPressure(s), 0) / list.length;
      return { district, count: list.length, capacity, pressure };
    })
    .filter((row) => row.count >= TWIN_INSIGHT.districtMinStations);
  const byCapacity = [...rows].sort((a, b) => b.capacity - a.capacity);
  const mismatch = rows
    .filter((row) => row.pressure > cityMeanPressure && row.capacity < totalDocks / Math.max(rows.length, 1))
    .sort((a, b) => b.pressure - a.pressure);
  const findings = [
    `全市柱位 ${totalDocks}，單站中位數 ${median} 柱。容量較密的行政區是${listNames(topDistricts(byCapacity)) || "—"}。`,
  ];
  if (mismatch.length) {
    findings.push(`壓力高於全市、柱位卻偏低的區：${listNames(mismatch.slice(0, TWIN_INSIGHT.topN).map((row) => row.district))}，供需空間可能錯位。`);
  }
  return {
    ...emptyLayer("density", { dataMode: "real" }),
    metrics: [
      { label: "總柱位", value: totalDocks, unit: "" },
      { label: "中位柱位", value: median, unit: "" },
    ],
    findings,
    evidence: byCapacity.slice(0, TWIN_INSIGHT.topN).map((row) => ({
      district: row.district,
      label: row.district,
      detail: `${row.capacity} 柱／${row.count} 站`,
    })),
    caveats: ["密度用總柱位，不是歷史借還量；錯位是行政區加總，不是選址模型。"],
  };
}

export function computeCoverageGaps(stations, {
  steps = TWIN_INSIGHT.coverageSteps,
  padDeg = TWIN_INSIGHT.coveragePadDeg,
  thresholdKm = TWIN_INSIGHT.gapThresholdKm,
} = {}) {
  const index = buildSpatialIndex(stations, 2);
  if (index.stations.length < 2) {
    return { medianKm: null, maxKm: null, overShare: null, overCount: 0, cells: 0 };
  }
  const lngs = index.stations.map((s) => Number(s.lng));
  const lats = index.stations.map((s) => Number(s.lat));
  const minLng = Math.min(...lngs) - padDeg;
  const maxLng = Math.max(...lngs) + padDeg;
  const minLat = Math.min(...lats) - padDeg;
  const maxLat = Math.max(...lats) + padDeg;
  const gaps = [];
  for (let i = 0; i <= steps; i += 1) {
    for (let j = 0; j <= steps; j += 1) {
      const lng = minLng + ((maxLng - minLng) * i) / steps;
      const lat = minLat + ((maxLat - minLat) * j) / steps;
      gaps.push(nearestStationKm(index, lat, lng, TWIN_INSIGHT.coverageCapKm));
    }
  }
  const sorted = gaps.slice().sort((a, b) => a - b);
  const overCount = gaps.filter((gap) => gap > thresholdKm).length;
  return {
    medianKm: sorted[Math.floor(sorted.length / 2)],
    maxKm: sorted[sorted.length - 1],
    overShare: pct(overCount, gaps.length),
    overCount,
    cells: gaps.length,
  };
}

export function buildCoverageInsight(stations) {
  const gaps = computeCoverageGaps(stations);
  if (gaps.medianKm == null) {
    return emptyLayer("coverage", {
      dataMode: "real",
      caveats: ["有效座標不足，無法估計覆蓋缺口。"],
    });
  }
  return {
    ...emptyLayer("coverage", { dataMode: "real" }),
    metrics: [
      { label: "最近站中位距離", value: round(gaps.medianKm, 2), unit: "km" },
      { label: `>${TWIN_INSIGHT.gapThresholdKm} km 格點`, value: gaps.overShare, unit: "%" },
    ],
    findings: [
      `站網凸包內，到最近站的直線距離中位數 ${round(gaps.medianKm, 2)} km；超過 ${TWIN_INSIGHT.gapThresholdKm} km 的格點佔 ${gaps.overShare}%。`,
    ],
    evidence: [],
    caveats: [
      "只評站網範圍內的格點，沒有人口加權；山區空地與市區死角看起來一樣紅。",
      "直線距離，不是走路或騎車等時圈。",
    ],
  };
}

export function computeCatchmentStats(stations, radiusKm) {
  const index = buildSpatialIndex(stations, Math.max(radiusKm, 0.5));
  let isolated = 0;
  let overlapSum = 0;
  const isolatedStations = [];
  for (let i = 0; i < index.stations.length; i += 1) {
    const station = index.stations[i];
    const neighbors = queryNearbyIndices(index, Number(station.lat), Number(station.lng), radiusKm)
      .filter((idx) => idx !== i);
    overlapSum += neighbors.length;
    if (!neighbors.length) {
      isolated += 1;
      isolatedStations.push(station);
    }
  }
  return {
    isolated,
    meanOverlap: index.stations.length ? round(overlapSum / index.stations.length, 1) : 0,
    isolatedStations,
  };
}

export function buildCatchmentInsight(stations, radiusKm) {
  const stats = computeCatchmentStats(stations, radiusKm);
  return {
    ...emptyLayer("catchment", { dataMode: "real" }),
    metrics: [
      { label: "服務半徑", value: radiusKm, unit: "km" },
      { label: "孤立站", value: stats.isolated, unit: "站" },
      { label: "平均重疊", value: stats.meanOverlap, unit: "站" },
    ],
    findings: [
      `${radiusKm} km 直線半徑下，孤立站 ${stats.isolated} 座，平均每站與 ${stats.meanOverlap} 站重疊。`,
    ],
    evidence: stats.isolatedStations.slice(0, 5).map((station) => ({
      station_id: station.station_id,
      label: station.station_name,
      district: station.district,
      detail: `${radiusKm} km 內無鄰站`,
    })),
    caveats: ["直線半徑近似集水區，真正等時圈需要路網。"],
  };
}

export function buildNetworkInsight(stations) {
  if (stations.length < 2) {
    return emptyLayer("network", {
      dataMode: "method",
      caveats: ["站點不足，無法建立鄰近網路。"],
    });
  }
  const edges = buildKnnNetwork(stations, { k: 3 });
  const centrality = degreeCentrality(stations, edges);
  const hubs = stations
    .map((station) => ({ station, score: centrality.get(station.station_id) || 0 }))
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);
  return {
    ...emptyLayer("network", { dataMode: "method" }),
    metrics: [
      { label: "連線數", value: edges.length, unit: "" },
      { label: "最高中心性", value: round(hubs[0]?.score ?? 0, 2), unit: "" },
    ],
    findings: [
      `地理鄰近中心性最高的是${listNames(hubs.slice(0, TWIN_INSIGHT.topN).map((row) => row.station.station_name)) || "—"}。這是空間樞紐，不是借還流量樞紐。`,
    ],
    evidence: hubs.map((row) => ({
      station_id: row.station.station_id,
      label: row.station.station_name,
      district: row.station.district,
      detail: `中心性 ${round(row.score, 2)}`,
    })),
    caveats: ["無真實 OD，連線只看最近 3 站的地理距離。"],
  };
}

export function buildFlowInsight(recommendations) {
  const pairs = pairDispatchFlows(recommendations);
  const stats = flowPairStats(pairs);
  if (!pairs.length) {
    return emptyLayer("flow", {
      dataMode: "method",
      caveats: ["沒有可配對的取車與補車建議，或缺少座標。這不是真實 trip OD。"],
    });
  }
  const nearest = [...pairs].sort((a, b) => a.km - b.km).slice(0, 5);
  return {
    ...emptyLayer("flow", { dataMode: "method" }),
    metrics: [
      { label: "示意配對數", value: stats.count, unit: "對" },
      { label: "中位距離", value: round(stats.medianKm, 2), unit: "km" },
      { label: "同區占比", value: stats.sameDistrictShare, unit: "%" },
    ],
    findings: [
      `以「同區最近、一對一」把 ${stats.count} 筆取車建議配到補車站，中位直線距離 ${round(stats.medianKm, 2)} km。`,
    ],
    evidence: nearest.map((pair) => ({
      station_id: pair.to.station_id,
      label: `${pair.from.station_name} → ${pair.to.station_name}`,
      district: pair.to.district,
      detail: `${round(pair.km, 2)} km${pair.sameDistrict ? "｜同區" : "｜跨區"}`,
    })),
    caveats: ["這是調度建議的示意配對，不是真實借還 OD，也不能當成派車路線。"],
  };
}

const BUILDERS = {
  gauge: (ctx) => buildGaugeInsight(ctx.stations),
  kde: (ctx) => buildKdeInsight(ctx.stations),
  voronoi: (ctx) => buildVoronoiInsight(ctx.stations),
  density: (ctx) => buildDensityInsight(ctx.stations),
  coverage: (ctx) => buildCoverageInsight(ctx.stations),
  catchment: (ctx) => buildCatchmentInsight(ctx.stations, ctx.catchmentKm),
  network: (ctx) => buildNetworkInsight(ctx.stations),
  flow: (ctx) => buildFlowInsight(ctx.recommendations),
};

export function cityWideGate({ mode, stations, temporalCovered, temporalAvailable }) {
  const total = stations.length;
  if (total < 3) {
    return { cityWideOk: false, reason: "有效站點少於 3，不足以做全市空間解讀。" };
  }
  if (mode === "live") {
    return { cityWideOk: true, reason: null };
  }
  const covered = Number(temporalCovered) || 0;
  const ratio = covered / total;
  if (ratio >= TWIN_INSIGHT.cityWideCoverage) {
    return { cityWideOk: true, reason: null };
  }
  const available = Number(temporalAvailable) || covered;
  return {
    cityWideOk: false,
    reason: `時間機器不是即時，且僅 ${covered}/${total} 站有對應樣本（可用來源 ${available}）。覆蓋率未達 ${Math.round(TWIN_INSIGHT.cityWideCoverage * 100)}%，全市結論已關閉。`,
  };
}

export function compareEmptyRate(liveStations, otherStations) {
  if (!liveStations?.length || !otherStations?.length) return null;
  const live = emptyRate(liveStations);
  const other = emptyRate(otherStations);
  return { live, other, delta: round(other - live, 1) };
}

export function buildHeadline(layers, comparison) {
  const usable = (layers ?? []).filter((layer) => layer.findings.length);
  if (!usable.length) return null;
  const parts = [];
  if (comparison) {
    const sign = comparison.delta > 0 ? "+" : "";
    parts.push(`相對即時空站率 ${comparison.live}% → ${comparison.other}%（${sign}${comparison.delta} ppt）。`);
  }
  parts.push(...usable.slice(0, 3).map((layer) => layer.findings[0]));
  return parts.join(" ");
}

export function buildTwinInsights({
  stations,
  liveStations = null,
  recommendations = [],
  activeLayers = [],
  mode = "live",
  catchmentKm = 0.6,
  temporalCovered = 0,
  temporalAvailable = 0,
  stationsSource = "unknown",
  observedAt = null,
} = {}) {
  const usable = stationsWithCoords(stations);
  const gate = cityWideGate({
    mode,
    stations: usable,
    temporalCovered,
    temporalAvailable,
  });
  const ctx = { stations: usable, catchmentKm, recommendations };
  const layers = (activeLayers.length ? activeLayers : []).map((key) => {
    const builder = BUILDERS[key];
    if (!builder) return emptyLayer(key, { caveats: ["未知圖層。"] });
    if (key === "flow") return builder(ctx);
    if (!gate.cityWideOk) {
      return blockedLayer(key, gate.reason, { dataMode: catalogOf(key).dataMode });
    }
    if (!usable.length) {
      return blockedLayer(key, "沒有帶座標的站點，無法解讀。");
    }
    return builder(ctx);
  });
  const comparison = mode === "live" ? null : compareEmptyRate(liveStations, usable);

  return {
    cityWideOk: gate.cityWideOk,
    gateReason: gate.reason,
    nStations: usable.length,
    observedAt: observedAt || pickObservedAt(usable),
    stationsSource,
    mode,
    headline: gate.cityWideOk ? buildHeadline(layers, comparison) : null,
    comparison: gate.cityWideOk ? comparison : null,
    layers,
  };
}
