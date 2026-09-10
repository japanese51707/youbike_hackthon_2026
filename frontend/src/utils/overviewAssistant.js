// 長官頁「AI 營運助理」的規則型邏輯（Demo，非真實 LLM）。
// 摘要與回答全部由既有營運資料確定性產生；問到範圍外誠實回覆，不捏造。
// 不呼叫任何外部服務、無金鑰、無出向請求；不進派遣 payload。

// Demo 目標值（待交通局定義）
export const SERVICE_TARGETS = { empty_rate: 6, full_rate: 3 };

// 助理是「決策支援顧問」：只建議、示警，不自行決策（ADR-301／ADR-004）。
const ADVISORY_NOTE = "（我僅提供理解與建議；是否調度由規則引擎與人工決定）";

export function aggregateDistricts(data) {
  const map = {};
  for (const s of data.stations) {
    const d = s.district || "其他";
    map[d] ??= { district: d, count: 0, empty: 0, full: 0, usageSum: 0, stations: [] };
    map[d].count += 1;
    if (s.status === "empty") map[d].empty += 1;
    if (s.status === "full") map[d].full += 1;
    map[d].usageSum += Number(s.usage_rate) || 0;
    map[d].stations.push(s);
  }
  return Object.values(map)
    .map((r) => ({ ...r, avg: Math.round(r.usageSum / r.count), problems: r.empty + r.full }))
    .sort((a, b) => b.problems - a.problems || b.avg - a.avg);
}

function improvementText(data) {
  const sim = data.simulation;
  const parts = sim["指標"].map((label, i) => {
    const actual = Number(sim["實際歷史"][i]);
    const model = Number(sim["本系統模擬"][i]);
    const pct = actual ? Math.round(((actual - model) / actual) * 100) : 0;
    const arrow = pct >= 0 ? "↓" : "↑";
    return `${label.replace("(%)", "")} ${arrow}${Math.abs(pct)}%`;
  });
  return `模擬成效（實際 vs 本系統）：${parts.join("、")}。`;
}

// 決策建議（交通調度知識的規則型判斷；僅建議，非系統決策）
function decisionHint(data) {
  const { kpi, overview } = data;
  const empty = overview.station_summary.empty_stations;
  const full = overview.station_summary.full_stations;
  const emptyOver = kpi.empty_rate > SERVICE_TARGETS.empty_rate;
  const fullOver = kpi.full_rate > SERVICE_TARGETS.full_rate;
  const hot = aggregateDistricts(data)[0];

  if (empty === 0 && full === 0) return "目前無空/滿站，維持巡檢即可。";
  const parts = [];
  if (empty > 0) {
    parts.push(
      `建議優先處理空站（借不到車對民眾影響最直接）：目前 ${empty} 站空、${emptyOver ? "已超標" : "尚在目標內"}`,
    );
  }
  if (full > 0) {
    parts.push(`其次處理滿站 ${full} 站（還不到車）${fullOver ? "、已超標" : ""}`);
  }
  if (hot && hot.problems > 0) parts.push(`可從 ${hot.district} 著手`);
  return `${parts.join("；")}。實際派遣順序由規則引擎依緊急度決定`;
}

export function summarizeOverview(data) {
  const { kpi, overview } = data;
  const emptyOk = kpi.empty_rate <= SERVICE_TARGETS.empty_rate;
  const fullOk = kpi.full_rate <= SERVICE_TARGETS.full_rate;
  const hot = aggregateDistricts(data)[0];

  const lines = [
    `整體服務水準：${emptyOk && fullOk ? "達標 ✅" : "需注意 ⚠️"}`,
    `空站率 ${kpi.empty_rate}%（目標<${SERVICE_TARGETS.empty_rate}%，${emptyOk ? "達標" : "超標"}）；滿站率 ${kpi.full_rate}%（目標<${SERVICE_TARGETS.full_rate}%，${fullOk ? "達標" : "超標"}）。`,
    `需調度 ${overview.station_summary.need_dispatch} 站（空 ${overview.station_summary.empty_stations}／滿 ${overview.station_summary.full_stations}）。`,
  ];
  if (hot && hot.problems > 0) {
    lines.push(`最需關注：${hot.district}（問題站 ${hot.problems}）。`);
  }
  lines.push(improvementText(data));
  lines.push(
    `人力值勤 ${overview.operators.on_duty} 人；今日完成 ${overview.today_totals.completed_tasks} 件、移動 ${overview.today_totals.total_bikes_moved} 台。`,
  );
  // 決策支援：交通調度知識 — 空站(借不到車)對民眾影響最直接，優先於滿站
  const priorityHint = decisionHint(data);
  if (priorityHint) lines.push(`💡 ${priorityHint}`);
  lines.push(ADVISORY_NOTE);
  return lines;
}

export function answerOverview(data, question) {
  const q = String(question || "");
  const { kpi, overview } = data;
  const hot = aggregateDistricts(data)[0];

  if (/達標|服務水準|水準/.test(q)) {
    const emptyOk = kpi.empty_rate <= SERVICE_TARGETS.empty_rate;
    const fullOk = kpi.full_rate <= SERVICE_TARGETS.full_rate;
    return `空站率 ${kpi.empty_rate}%（${emptyOk ? "達標" : "超標"}）、滿站率 ${kpi.full_rate}%（${fullOk ? "達標" : "超標"}）；整體${emptyOk && fullOk ? "達標" : "需注意"}。（目標為 Demo 設定）`;
  }
  if (/空站/.test(q)) {
    return `目前空站 ${overview.station_summary.empty_stations} 站，空站率 ${kpi.empty_rate}%（目標<${SERVICE_TARGETS.empty_rate}%）。`;
  }
  if (/滿站/.test(q)) {
    return `目前滿站 ${overview.station_summary.full_stations} 站，滿站率 ${kpi.full_rate}%（目標<${SERVICE_TARGETS.full_rate}%）。`;
  }
  if (/哪|熱點|嚴重|問題|行政區|區/.test(q)) {
    return hot && hot.problems > 0
      ? `最需關注的是 ${hot.district}，問題站 ${hot.problems} 個（空 ${hot.empty}／滿 ${hot.full}），平均使用率 ${hot.avg}%。`
      : "目前各區沒有明顯問題站。";
  }
  if (/油資|成本|里程|花費|預算/.test(q)) {
    return `今日行駛 ${overview.today_totals.total_distance_km} km、預估油資 ${overview.today_totals.estimated_fuel_cost} 元，移動 ${overview.today_totals.total_bikes_moved} 台。`;
  }
  if (/人力|人員|司機|調度員/.test(q)) {
    return `值勤 ${overview.operators.on_duty} 人（執行中 ${overview.operators.busy}／休息 ${overview.operators.resting}／離勤 ${overview.operators.off_duty}）。`;
  }
  if (/需調度|調度|幾站/.test(q)) {
    return `目前需調度 ${overview.station_summary.need_dispatch} 站。`;
  }
  if (/改善|成效|模擬|before|after/i.test(q)) {
    return improvementText(data);
  }
  if (/任務|完成|緊急/.test(q)) {
    return `今日完成 ${overview.today_totals.completed_tasks} 件、等待 ${overview.today_totals.pending_tasks} 件、緊急 ${overview.today_totals.emergency_tasks} 件。`;
  }
  if (/優先|建議|該怎麼|怎麼做|決策|先處理|先調度|如何/.test(q)) {
    return `${decisionHint(data)}。${ADVISORY_NOTE}`;
  }
  return "我是 Demo 規則型助理（決策支援用），可回答：服務水準／達標、空站、滿站、需調度、熱點行政區、人力、成本油資、改善成效、任務量，以及「該優先處理什麼」的建議。試著問問看。";
}
