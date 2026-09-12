// 調度建議 → 示意取補配對。不是真實 trip OD，也不進派工。
import { haversineKm } from "./geo.js";

function hasCoords(row) {
  return Number.isFinite(Number(row?.lat)) && Number.isFinite(Number(row?.lng));
}

function byAction(recommendations, action) {
  return (recommendations ?? []).filter((row) => row.action === action && hasCoords(row));
}

function pairScore(pickup, dropoff) {
  const km = haversineKm(pickup, dropoff);
  const same = pickup.district && pickup.district === dropoff.district;
  return { km, same, rank: same ? km : km + 1000 };
}

export function pairDispatchFlows(recommendations) {
  const pickups = byAction(recommendations, "取車")
    .slice()
    .sort((a, b) => (Number(b.quantity) || 0) - (Number(a.quantity) || 0));
  const dropoffs = byAction(recommendations, "補車");
  const used = new Set();
  const pairs = [];

  for (const pickup of pickups) {
    let best = null;
    for (const dropoff of dropoffs) {
      if (used.has(dropoff.station_id) || dropoff.station_id === pickup.station_id) continue;
      const score = pairScore(pickup, dropoff);
      if (!best || score.rank < best.rank) best = { dropoff, ...score };
    }
    if (!best) continue;
    used.add(best.dropoff.station_id);
    pairs.push({
      from: pickup,
      to: best.dropoff,
      km: best.km,
      sameDistrict: best.same,
      quantity: Number(best.dropoff.quantity) || Number(pickup.quantity) || 0,
    });
  }

  return pairs;
}

export function flowPairStats(pairs) {
  if (!pairs.length) {
    return { count: 0, medianKm: null, sameDistrictShare: 0 };
  }
  const distances = pairs.map((pair) => pair.km).sort((a, b) => a - b);
  const same = pairs.filter((pair) => pair.sameDistrict).length;
  return {
    count: pairs.length,
    medianKm: distances[Math.floor(distances.length / 2)],
    sameDistrictShare: Math.round((same / pairs.length) * 1000) / 10,
  };
}
