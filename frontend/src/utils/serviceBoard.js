/** 服務水準看板（ADR-209）用的確定性彙總。不造 Before/After、不派工。 */

export const SERVICE_REF_THRESHOLDS = { empty_rate: 6, full_rate: 3, health_rate: 90, offline_rate: 4 };

export function pct(part, whole, digits = 1) {
  const den = Number(whole) || 0;
  if (!den) return 0;
  return Number(((Number(part) || 0) * 100 / den).toFixed(digits));
}

export function ratesFromKpi(kpi) {
  const inService = Number(kpi?.in_service_stations) || 0;
  const empty = Number(kpi?.empty_stations) || 0;
  const full = Number(kpi?.full_stations) || 0;
  const healthy = Number(kpi?.healthy_stations) || 0;
  const offline = Number(kpi?.offline_stations) || 0;
  const total = Number(kpi?.total_stations) || 0;
  return {
    empty,
    full,
    healthy,
    offline,
    total,
    inService,
    emptyRate: pct(empty, inService),
    fullRate: pct(full, inService),
    healthRate: Number(kpi?.health_rate_pct ?? pct(healthy, inService)),
    offlineRate: pct(offline, total),
  };
}

export function rankDistrictPressure(stations) {
  const map = {};
  for (const s of stations ?? []) {
    const district = s.district || "未分區";
    map[district] ??= { district, count: 0, empty: 0, full: 0, stations: [] };
    map[district].count += 1;
    if (s.status === "empty") map[district].empty += 1;
    if (s.status === "full") map[district].full += 1;
    if (s.status === "empty" || s.status === "full") {
      map[district].stations.push(s);
    }
  }
  return Object.values(map)
    .map((row) => {
      const problems = row.empty + row.full;
      return { ...row, problems, pressure: districtPressureLevel(problems, row.count) };
    })
    .sort((a, b) => b.problems - a.problems || b.empty - a.empty || a.district.localeCompare(b.district, "zh-Hant"));
}

/** 行政區壓力色：綠＝沒有空滿、黃＝有但未過 8%、紅＝空滿佔該區 ≥8%。 */
export function districtPressureLevel(problems, count) {
  const total = Number(count) || 0;
  const n = Number(problems) || 0;
  if (!total) return "none";
  if (n <= 0) return "green";
  return (n * 100) / total >= 8 ? "red" : "yellow";
}

export function buildHeadline({ empty, full, hotDistricts }) {
  const focus = hotDistricts?.length
    ? `；${hotDistricts.join("、")}需關注`
    : "；各區大致穩定";
  return `目前 ${empty} 站借不到、${full} 站還不到${focus}。`;
}

export function districtServiceRows(stations) {
  const map = {};
  for (const s of stations ?? []) {
    const district = s.district || "未分區";
    map[district] ??= {
      district,
      count: 0,
      empty: 0,
      full: 0,
      healthy: 0,
      offline: 0,
      emptyStations: [],
      fullStations: [],
      offlineStations: [],
    };
    const row = map[district];
    row.count += 1;
    if (s.status === "empty") {
      row.empty += 1;
      row.emptyStations.push(s);
    } else if (s.status === "full") {
      row.full += 1;
      row.fullStations.push(s);
    } else if (s.status === "offline") {
      row.offline += 1;
      row.offlineStations.push(s);
    } else {
      row.healthy += 1;
    }
  }
  return Object.values(map).map((row) => {
    const inService = row.count - row.offline;
    return {
      ...row,
      inService,
      emptyRate: pct(row.empty, inService),
      fullRate: pct(row.full, inService),
      healthRate: pct(row.healthy, inService),
      offlineRate: pct(row.offline, row.count),
    };
  });
}

export function dutyCounts(operators) {
  const rows = operators ?? [];
  const onDuty = rows.filter((o) => o.status === "on_duty" || o.status === "busy").length;
  const busy = rows.filter((o) => o.status === "busy").length;
  return { total: rows.length, onDuty, busy };
}

export function elapsedMinutesSince(openedAt, nowMs = Date.now()) {
  const started = Date.parse(openedAt);
  if (!Number.isFinite(started)) return null;
  return Math.max(0, (nowMs - started) / 60000);
}

export function formatDurationMinutes(minutes) {
  if (minutes == null || Number.isNaN(Number(minutes))) return "—";
  const total = Math.max(0, Math.round(Number(minutes)));
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  if (hours <= 0) return `${rest} 分`;
  if (rest === 0) return `${hours} 時`;
  return `${hours} 時 ${rest} 分`;
}

export function openProblemsByStation(problems) {
  const map = new Map();
  for (const item of problems?.open ?? []) {
    if (item?.station_id) map.set(item.station_id, item);
  }
  return map;
}

export function districtLongestOpen(district, problems, nowMs = Date.now()) {
  const rows = (problems?.open ?? []).filter((item) => item.district === district);
  if (!rows.length) return null;
  return Math.max(...rows.map((item) => elapsedMinutesSince(item.opened_at, nowMs) ?? item.elapsed_minutes ?? 0));
}

export function collectedMinutes(history, nowMs = Date.now()) {
  const raw = history?.collected_minutes;
  if (raw != null && Number.isFinite(Number(raw))) return Number(raw);
  const first = Date.parse(history?.first_observed_at);
  const last = Date.parse(history?.last_observed_at || nowMs);
  if (!Number.isFinite(first) || !Number.isFinite(last)) return null;
  return Math.max(0, (last - first) / 60000);
}

export function resolveCardCopy({ city = {}, history = {}, longestOpen, liveProblems = 0 } = {}) {
  const resolved = Number(city.resolved_count) || 0;
  const avg = city.avg_resolved_minutes;
  const collected = collectedMinutes(history);
  const collectedText = collected == null
    ? ""
    : collected < 60
      ? `已收集 ${Math.round(collected)} 分`
      : `已收集 ${formatDurationMinutes(collected)}`;
  if (avg != null) {
    return {
      value: formatDurationMinutes(avg),
      timer: longestOpen == null ? "目前沒有進行中的空／滿" : `進行中最長 ${formatDurationMinutes(longestOpen)}`,
      hint: `${collectedText ? `${collectedText}｜` : ""}近 24 時內已排除 ${resolved} 件｜點開看各區`,
    };
  }
  if (longestOpen != null) {
    return {
      value: formatDurationMinutes(longestOpen),
      timer: "尚無排除，先看進行中最長",
      hint: `${collectedText || "未滿 24 時也會算"}｜點開看各區`,
    };
  }
  if (liveProblems > 0) {
    return {
      value: `${liveProblems} 站`,
      timer: "時計還沒接上，先看目前空／滿數",
      hint: "未滿 24 時也會顯示已有資料｜點開看各區",
    };
  }
  return {
    value: "—",
    timer: "目前沒有空／滿站",
    hint: collectedText ? `${collectedText}，窗口內尚無空滿` : "窗口內尚無空滿｜未滿 24 時也會算",
  };
}

export function longestOpenOfKind(problems, kind, nowMs = Date.now()) {
  const values = (problems?.open ?? [])
    .filter((item) => !kind || item.kind === kind)
    .map((item) => elapsedMinutesSince(item.opened_at, nowMs) ?? item.elapsed_minutes)
    .filter((value) => value != null);
  return values.length ? Math.max(...values) : null;
}
