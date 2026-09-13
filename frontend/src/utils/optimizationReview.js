/** 戰情室最適化審核：中文標籤、示意資料、逐站決定。不派工（ADR-004／120）。 */

export const PARAM_LABELS = {
  base_outflow_coef: "平日流出係數",
  base_target_coef: "目標水位係數",
  env_coef_rain: "雨天敏感度",
  env_coef_heavy_rain: "豪雨敏感度",
  env_coef_weekend: "假日敏感度",
  env_coef_holiday: "連假敏感度",
  env_coef_event: "活動敏感度",
};

export const DECISION_LABELS = {
  accept: "接受建議",
  keep: "維持原值",
  re_adjust: "改建議值",
};

export function paramLabel(param) {
  return PARAM_LABELS[param] || param;
}

export function formatSignedPct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  const rounded = Math.round(n * 10) / 10;
  return `${rounded > 0 ? "+" : ""}${rounded}%`;
}

export function isReviewActionable(review) {
  return review?.status === "ok" && Array.isArray(review.station_changes) && review.station_changes.length > 0;
}

export function createMockReview(reviewDate = "2026-09-13") {
  const stations = [
    {
      station_id: "500101002",
      station_name: "捷運景安站",
      district: "中和區",
      is_significant: true,
      why: "近 3 天平日早上流出比基準高，空站來得比較快。",
      params: [
        { param: "base_outflow_coef", old: 1, new: 1.08, change_pct: 8, reason: "平日尖峰流出偏高" },
      ],
    },
    {
      station_id: "500103005",
      station_name: "三重國小",
      district: "三重區",
      is_significant: true,
      why: "放學時段還車偏多，滿站比基準更常出現。",
      params: [
        { param: "base_outflow_coef", old: 1, new: 0.93, change_pct: -7, reason: "到站還車偏多" },
        { param: "env_coef_weekend", old: 1, new: 0.96, change_pct: -4, reason: "週末滿站殘差" },
      ],
    },
    {
      station_id: "500102010",
      station_name: "板橋車站",
      district: "板橋區",
      is_significant: false,
      why: "轉乘站假日需求略低於基準，建議小幅下修假日敏感度。",
      params: [
        { param: "env_coef_weekend", old: 1, new: 0.95, change_pct: -5, reason: "假日轉乘需求略低" },
      ],
    },
    {
      station_id: "500105011",
      station_name: "蘆洲國民運動中心",
      district: "蘆洲區",
      is_significant: false,
      why: "雨天借車下降比全市平均更明顯。",
      params: [
        { param: "env_coef_rain", old: 1, new: 0.92, change_pct: -8, reason: "雨天借車下降較多" },
      ],
    },
  ];
  const pcts = stations.flatMap((row) => row.params.map((item) => Math.abs(item.change_pct)));
  return {
    review_id: `REV-MOCK-${reviewDate.replaceAll("-", "")}`,
    review_date: reviewDate,
    lookback_days: 3,
    status: "ok",
    approval_state: "pending_approval",
    coefficient_mode: "off",
    mock: true,
    reason: "近 3 天偏差檢視後，建議調整以下站點係數。",
    effective_note: "核准後寫入可回溯的參數版本。",
    summary: {
      total_stations_adjusted: stations.length,
      avg_change_pct: Math.round((pcts.reduce((sum, n) => sum + n, 0) / pcts.length) * 10) / 10,
      significant_count: stations.filter((row) => row.is_significant).length,
    },
    station_changes: stations,
    diagnostics: { skipped_insufficient: 12, stations_considered: 86 },
  };
}

export function applyStationDecision(changes, stationId, decision) {
  return (changes || []).map((row) => (
    row.station_id === stationId ? { ...row, decision } : row
  ));
}

export function summarizeReviewDecisions(changes) {
  const rows = changes || [];
  const accept = rows.filter((row) => (row.decision || "accept") !== "keep");
  const keep = rows.filter((row) => row.decision === "keep");
  return {
    acceptCount: accept.length,
    keepCount: keep.length,
    acceptNames: accept.map((row) => row.station_name || row.station_id),
    keepNames: keep.map((row) => row.station_name || row.station_id),
  };
}

export function describeParamChange(item) {
  return `${paramLabel(item.param)} ${item.old} → ${item.new}（${formatSignedPct(item.change_pct)}）`;
}
