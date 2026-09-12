// 戰情室流向弧線的示意資料。不是真實 trip OD，也不進派工。
// 依當前使用率把偏滿站連到附近偏空站；一站可連多站，讓弧線看起來更密。

import { haversineKm } from "./geo.js";
import { pairDispatchFlows } from "./twinFlow.js";

const MOCK_FLOW = {
  surplusMin: 55,
  deficitMax: 45,
  perDistrict: 28,
  neighbors: 5,
  hubNeighbors: 8,
  hubCount: 18,
  maxKm: 12,
  maxPairs: 360,
  fallbackEach: 12,
};

function hasCoords(station) {
  return Number.isFinite(Number(station?.lat)) && Number.isFinite(Number(station?.lng));
}

function usageOf(station) {
  const usage = Number(station?.usage_rate);
  if (Number.isFinite(usage)) return usage;
  const docks = Number(station?.total_docks);
  const bikes = Number(station?.available_bikes);
  if (!docks || !Number.isFinite(bikes)) return 50;
  return (bikes / docks) * 100;
}

function isSurplus(station) {
  return station.status === "full" || station.status === "high" || usageOf(station) >= MOCK_FLOW.surplusMin;
}

function isDeficit(station) {
  return station.status === "empty" || station.status === "low" || usageOf(station) <= MOCK_FLOW.deficitMax;
}

function quantityFor(from, to) {
  const surplus = Math.max(4, Math.round(usageOf(from) - 50));
  const deficit = Math.max(4, Math.round(50 - usageOf(to)));
  return Math.max(4, Math.min(18, Math.round((surplus + deficit) / 2)));
}

function toEndpoint(station, action) {
  return {
    recommendation_id: `FLOW-MOCK-${action}-${station.station_id}`,
    station_id: station.station_id,
    station_name: station.station_name,
    district: station.district,
    action,
    quantity: quantityFor(station, station),
    lat: Number(station.lat),
    lng: Number(station.lng),
    source: "status-mock",
  };
}

function groupByDistrict(stations) {
  const groups = new Map();
  for (const station of stations ?? []) {
    if (!hasCoords(station)) continue;
    const key = station.district || "未分區";
    const list = groups.get(key) ?? [];
    list.push(station);
    groups.set(key, list);
  }
  return groups;
}

function pickEnds(stations, { surplusMin, deficitMax, perDistrict, fallbackEach }) {
  const pickups = [];
  const dropoffs = [];
  for (const list of groupByDistrict(stations).values()) {
    const ranked = list.slice().sort((a, b) => usageOf(b) - usageOf(a));
    const surplus = ranked.filter((row) => usageOf(row) >= surplusMin || isSurplus(row)).slice(0, perDistrict);
    const deficit = ranked
      .filter((row) => usageOf(row) <= deficitMax || isDeficit(row))
      .sort((a, b) => usageOf(a) - usageOf(b))
      .slice(0, perDistrict);
    const take = Math.min(fallbackEach ?? 12, ranked.length);
    const fallbackPick = surplus.length ? surplus : ranked.slice(0, take);
    const fallbackDrop = deficit.length ? deficit : ranked.slice(-take).reverse();
    pickups.push(...fallbackPick);
    dropoffs.push(...fallbackDrop);
  }
  return { pickups: uniqueStations(pickups), dropoffs: uniqueStations(dropoffs) };
}

function uniqueStations(stations) {
  const seen = new Set();
  return stations.filter((row) => {
    if (!row?.station_id || seen.has(row.station_id)) return false;
    seen.add(row.station_id);
    return true;
  });
}

function pairKey(fromId, toId) {
  return `${fromId}->${toId}`;
}

export function pairMockFlows(stations, options = {}) {
  const cfg = { ...MOCK_FLOW, ...options };
  const { pickups, dropoffs } = pickEnds(stations, cfg);
  if (pickups.length < 1 || dropoffs.length < 1) return [];

  const hubIds = new Set(
    pickups
      .slice()
      .sort((a, b) => usageOf(b) - usageOf(a))
      .slice(0, cfg.hubCount)
      .map((row) => row.station_id),
  );

  const pairs = [];
  const seen = new Set();
  const addPair = (pickup, dropoff, km, same) => {
    const key = pairKey(pickup.station_id, dropoff.station_id);
    if (seen.has(key)) return;
    seen.add(key);
    pairs.push({
      from: toEndpoint(pickup, "取車"),
      to: toEndpoint(dropoff, "補車"),
      km,
      sameDistrict: same,
      quantity: quantityFor(pickup, dropoff),
    });
  };

  const scoreLink = (from, to) => {
    const km = haversineKm(from, to);
    const same = Boolean(from.district && from.district === to.district);
    return { km, same, rank: same ? km : km + 1.4 };
  };

  for (const pickup of pickups) {
    const take = hubIds.has(pickup.station_id) ? cfg.hubNeighbors : cfg.neighbors;
    dropoffs
      .filter((dropoff) => dropoff.station_id !== pickup.station_id)
      .map((dropoff) => ({ dropoff, ...scoreLink(pickup, dropoff) }))
      .filter((row) => Number.isFinite(row.km) && row.km <= cfg.maxKm)
      .sort((a, b) => a.rank - b.rank || a.km - b.km)
      .slice(0, take)
      .forEach((row) => addPair(pickup, row.dropoff, row.km, row.same));
  }

  for (const dropoff of dropoffs) {
    pickups
      .filter((pickup) => pickup.station_id !== dropoff.station_id)
      .map((pickup) => ({ pickup, ...scoreLink(pickup, dropoff) }))
      .filter((row) => Number.isFinite(row.km) && row.km <= cfg.maxKm)
      .sort((a, b) => a.rank - b.rank || a.km - b.km)
      .slice(0, cfg.neighbors)
      .forEach((row) => addPair(row.pickup, dropoff, row.km, row.same));
  }

  return pairs
    .sort((a, b) => Number(b.sameDistrict) - Number(a.sameDistrict) || a.km - b.km)
    .slice(0, cfg.maxPairs);
}

export function buildMockFlowRecommendations(stations, options) {
  const pairs = pairMockFlows(stations, options);
  const recs = [];
  const seen = new Set();
  for (const pair of pairs) {
    for (const row of [pair.from, pair.to]) {
      if (seen.has(row.station_id)) continue;
      seen.add(row.station_id);
      recs.push(row);
    }
  }
  return recs;
}

export function resolveTwinFlowRecommendations({ stations, recommendations } = {}) {
  const mockPairs = pairMockFlows(stations);
  if (mockPairs.length) {
    return {
      recommendations: buildMockFlowRecommendations(stations),
      source: "status-mock",
      pairs: mockPairs,
    };
  }
  const dispatchPairs = pairDispatchFlows(recommendations);
  return {
    recommendations: recommendations ?? [],
    source: dispatchPairs.length ? "dispatch" : "status-mock",
    pairs: dispatchPairs,
  };
}
