export const FAULT_STORAGE_KEY = "rider-fault-summaries";
export const QUANTITY_ISSUES = new Set(["bike", "dock"]);
export const FAULT_ISSUE_OPTIONS = [
  { value: "bike", label: "車壞了", unit: "台" },
  { value: "dock", label: "車柱故障", unit: "柱" },
  { value: "station", label: "整站不能用" },
  { value: "other", label: "其他" },
];

export function needsFaultQuantity(issue) {
  return QUANTITY_ISSUES.has(issue);
}

export function clampFaultQuantity(value, max = 10) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 1;
  return Math.min(max, Math.max(1, Math.round(n)));
}

export function emptyFaultSummary(stationId, stationName) {
  return {
    station_id: stationId,
    station_name: stationName || stationId,
    bikes: 0,
    docks: 0,
    station_down: false,
    other: 0,
  };
}

export function addFaultDelta(summary, issue, addQuantity = 1) {
  const next = { ...emptyFaultSummary(summary?.station_id, summary?.station_name), ...summary };
  const add = clampFaultQuantity(addQuantity);
  if (issue === "bike") next.bikes += add;
  else if (issue === "dock") next.docks += add;
  else if (issue === "station") next.station_down = true;
  else next.other += 1;
  return next;
}

export function previewFaultAdd(summary, issue, addQuantity = 1) {
  const current = { ...emptyFaultSummary(summary?.station_id, summary?.station_name), ...summary };
  const add = needsFaultQuantity(issue) ? clampFaultQuantity(addQuantity) : issue === "other" ? 1 : 0;
  return { current, add, next: addFaultDelta(current, issue, addQuantity), issue };
}

export function formatFaultSummary(summary) {
  if (!summary) return "";
  const parts = [];
  if (summary.bikes > 0) parts.push(`${summary.bikes} 台`);
  if (summary.docks > 0) parts.push(`${summary.docks} 柱`);
  if (summary.station_down) parts.push("整站不能用");
  if (summary.other > 0) parts.push(`其他 ${summary.other} 則`);
  if (!parts.length) return "";
  return `本站已通報故障 ${parts.join("、")}`;
}

export function indexFaultSummaries(list = []) {
  return Object.fromEntries((list || []).filter((row) => row?.station_id).map((row) => [row.station_id, row]));
}

export function loadLocalFaultSummaries() {
  try {
    const parsed = JSON.parse(localStorage.getItem(FAULT_STORAGE_KEY) || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function persistLocalFaultSummaries(byId) {
  localStorage.setItem(FAULT_STORAGE_KEY, JSON.stringify(byId));
}
