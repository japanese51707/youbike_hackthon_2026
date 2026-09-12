// 戰情室顧問的 grounded context（ADR-311）。只精簡洞察，不送全市站點原文。

import { ANALYSIS_CATALOG, PENDING_ANALYSES } from "../config/analysisCatalog.js";
import { districtStatusRows } from "./twinInsights.js";

const ADVISORY_NOTE = "（我僅提供理解與建議；是否調度由規則引擎與人工決定）";

function compactStation(station) {
  return {
    station_id: station.station_id || undefined,
    station_name: station.station_name,
    district: station.district || undefined,
    status: station.status || undefined,
    available_bikes: Number.isFinite(Number(station.available_bikes))
      ? Number(station.available_bikes)
      : undefined,
  };
}

function compactEvidence(item) {
  if (!item) return null;
  if (typeof item === "string") return { label: item };
  return {
    label: item.label || item.district || item.station_name || undefined,
    detail: item.detail || undefined,
    station_id: item.station_id || undefined,
    district: item.district || undefined,
  };
}

export function compactTwinContext(report, { snapshot = [], visibleLayers } = {}) {
  const layers = (report?.layers ?? []).map((layer) => ({
    key: layer.key,
    title: layer.title,
    data_mode: layer.dataMode,
    metrics: (layer.metrics ?? []).slice(0, 8),
    findings: (layer.findings ?? []).slice(0, 6),
    caveats: (layer.caveats ?? []).slice(0, 6),
    evidence: (layer.evidence ?? []).slice(0, 6).map(compactEvidence).filter(Boolean),
  }));
  const empty = (snapshot ?? []).filter((s) => s.status === "empty").slice(0, 8).map(compactStation);
  const full = (snapshot ?? []).filter((s) => s.status === "full").slice(0, 8).map(compactStation);
  const districts = districtStatusRows(snapshot).slice(0, 8).map((row) => ({
    district: row.district,
    empty: row.empty,
    count: row.count,
    empty_rate: row.emptyRate,
  }));
  const active = visibleLayers ?? layers.map((layer) => layer.key);
  return {
    mode: report?.mode || "live",
    observed_at: report?.observedAt || undefined,
    n_stations: report?.nStations ?? snapshot.length,
    stations_source: report?.stationsSource || undefined,
    city_wide_ok: Boolean(report?.cityWideOk),
    gate_reason: report?.gateReason || undefined,
    headline: report?.headline || undefined,
    active_layers: active,
    layers,
    top_empty: empty,
    top_full: full,
    top_districts: districts,
    analysis_notes: [
      ...ANALYSIS_CATALOG.map((item) => ({
        key: item.key,
        name: item.name,
        info: `${item.purpose}。${item.info}`,
      })),
      ...PENDING_ANALYSES.map((info, index) => ({
        key: `pending-${index}`,
        name: "待接真實資料",
        info,
      })),
    ],
  };
}

export function fallbackTwinAnswer(context, question) {
  const q = String(question || "").trim();
  const modeLabel = { live: "即時", past: "歷史", predict: "預測" }[context.mode] || context.mode;
  const summary = () => {
    const lines = [
      `目前是${modeLabel}戰情，來源 ${context.stations_source || "不明"}，納入 ${context.n_stations} 站。`,
    ];
    if (context.observed_at) lines.push(`觀測時間 ${context.observed_at}。`);
    if (!context.city_wide_ok) {
      lines.push(context.gate_reason || "全市結論已關閉。");
    }
    if (context.headline) lines.push(context.headline);
    for (const layer of context.layers ?? []) {
      const finding = layer.findings?.[0];
      const caveat = layer.caveats?.[0] ? `限制：${layer.caveats[0]}` : "";
      if (finding) lines.push(`${layer.title}：${finding} ${caveat}`.trim());
    }
    const hot = context.top_districts?.[0];
    if (hot) lines.push(`空站較集中：${hot.district}（${hot.empty}/${hot.count}，${hot.empty_rate}%）。`);
    lines.push(ADVISORY_NOTE);
    return lines.join("\n");
  };

  if (!q || /總結|摘要|現況|情況|怎麼了/.test(q)) return summary();
  if (/派工|派遣|派車|派哪|去哪站|哪台車/.test(q)) {
    return `我不能決定或執行調度。派哪台車、去哪一站由規則引擎與人工閘門決定。${ADVISORY_NOTE}`;
  }
  if (/空站|哪一區|哪區|熱點|集中/.test(q) && context.top_districts?.[0]) {
    const hot = context.top_districts[0];
    return `依目前洞察，空站較集中在 ${hot.district}（${hot.empty}/${hot.count}，${hot.empty_rate}%）。${ADVISORY_NOTE}`;
  }
  if (/什麼意思|是什麼|怎麼算|方法|Gi|KDE|Voronoi|覆蓋|集水/.test(q) && context.analysis_notes?.length) {
    return `這頁分析方法如下。沒有出現在目前圖層的資料我不會編造。\n${context.analysis_notes.map((n) => `${n.name}：${n.info}`).join("\n")}`;
  }
  if (context.headline) return `我只能根據目前戰情數字回答。當前摘要：${context.headline} ${ADVISORY_NOTE}`;
  return `我是戰情室顧問（規則型降級）。可問現況總結、空站／哪一區、圖層方法。沒出現在洞察裡的數字會回「不可用」。`;
}
