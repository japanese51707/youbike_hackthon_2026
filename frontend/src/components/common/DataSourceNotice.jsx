import { Alert } from "antd";
import { formatDateTime } from "../../utils/formatters.js";

const labels = { youbike_official: "新北 YouBike 官方", tdx: "TDX", historical: "歷史資料", mock: "Mock 展示資料" };
export default function DataSourceNotice({ stations = [] }) {
  if (!stations.length) return null;
  const source = labels[stations[0].source] || stations[0].source || "來源未提供";
  const stale = stations.filter(s => s.data_freshness === "stale").length;
  const times = stations.map(s => s.observed_at).filter(Boolean).sort();
  return <Alert showIcon type={stale ? "warning" : "info"}
    title={`${source} · 觀測 ${formatDateTime(times[0])} ～ ${formatDateTime(times.at(-1))}${stale ? ` · ${stale} 站資料過期，暫停派工` : ""}`} />;
}
