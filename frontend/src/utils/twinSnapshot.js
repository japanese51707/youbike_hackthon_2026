// 戰情室時間快照：把歷史 frame／預測視野疊到即時站況上。缺值不插補。

export function statusFromUsage(bikes, docks, usage) {
  if (bikes <= 0) return "empty";
  if (docks <= 0) return "full";
  if (usage < 30) return "low";
  if (usage > 70) return "high";
  return "normal";
}

export function overlayBikes(station, bikes) {
  if (!Number.isFinite(Number(bikes))) return station;
  const cap = Number(station.total_docks) || 0;
  const nextBikes = Math.max(0, Number(bikes));
  const docks = Math.max(0, cap - nextBikes);
  const usage = cap ? Math.round((nextBikes / cap) * 1000) / 10 : station.usage_rate;
  return {
    ...station,
    available_bikes: nextBikes,
    available_docks: docks,
    usage_rate: usage,
    status: statusFromUsage(nextBikes, docks, usage),
  };
}

export function applyUpdates(stations, updates) {
  if (!updates?.size) {
    return { stations, covered: 0 };
  }
  let covered = 0;
  const next = stations.map((station) => {
    const bikes = updates.get(station.station_id);
    if (!Number.isFinite(Number(bikes))) return station;
    covered += 1;
    return overlayBikes(station, bikes);
  });
  return { stations: next, covered };
}

export function applyTemporalMock(stations, temporalStations, mode) {
  const available = temporalStations?.length ?? 0;
  if (mode === "live" || !temporalStations) {
    return { stations, covered: 0, available };
  }
  const updates = new Map();
  for (const row of temporalStations) {
    let bikes = null;
    if (mode === "past") bikes = row.past?.at(-1)?.availableBikes;
    if (mode === "predict") {
      const forecast =
        row.forecasts?.find((item) => item.offsetMinutes === 60 && item.isAvailable) ||
        row.forecasts?.find((item) => item.isAvailable);
      bikes = forecast?.availableBikes;
    }
    if (Number.isFinite(Number(bikes))) updates.set(row.stationId, bikes);
  }
  const applied = applyUpdates(stations, updates);
  return { stations: applied.stations, covered: applied.covered, available };
}

export function updatesFromHistoryFrame(frameStations) {
  const updates = new Map();
  for (const row of frameStations ?? []) {
    if (row?.station_id != null && Number.isFinite(Number(row.available_bikes))) {
      updates.set(row.station_id, Number(row.available_bikes));
    }
  }
  return updates;
}

export function updatesFromRecommendations(recommendations, horizon = 60) {
  const updates = new Map();
  const key = String(horizon);
  for (const row of recommendations ?? []) {
    const byHorizon = row.arrival_by_horizon?.[key] ?? row.arrival_by_horizon?.[horizon];
    const bikes = Number.isFinite(Number(byHorizon)) ? Number(byHorizon) : Number(row.predicted_at_arrival);
    if (row?.station_id && Number.isFinite(bikes)) updates.set(row.station_id, bikes);
  }
  return updates;
}

export function pickTimelineFrame(timeline, preferredTime = "08:00") {
  const frames = timeline?.frames ?? [];
  if (!frames.length) return null;
  const preferred = frames.find((frame) => frame.time === preferredTime);
  return preferred ?? frames[Math.floor(frames.length / 2)] ?? frames.at(-1);
}

export function buildTwinView({
  stations,
  mode,
  temporalStations,
  historyFrame,
  recommendations,
}) {
  if (mode === "live") {
    return { stations, covered: stations.length, available: stations.length, source: "live" };
  }

  if (mode === "past" && historyFrame?.stations?.length) {
    const applied = applyUpdates(stations, updatesFromHistoryFrame(historyFrame.stations));
    return {
      stations: applied.stations,
      covered: applied.covered,
      available: historyFrame.stations.length,
      source: "historical-frame",
    };
  }

  if (mode === "predict") {
    const recUpdates = updatesFromRecommendations(recommendations, 60);
    if (recUpdates.size) {
      const applied = applyUpdates(stations, recUpdates);
      return {
        stations: applied.stations,
        covered: applied.covered,
        available: recUpdates.size,
        source: "recommendation-horizon",
      };
    }
  }

  const mock = applyTemporalMock(stations, temporalStations, mode);
  return { ...mock, source: "temporal-mock" };
}

export function emptyRate(stations) {
  if (!stations?.length) return 0;
  const empty = stations.filter((station) => station.status === "empty").length;
  return Math.round((empty / stations.length) * 1000) / 10;
}
