import { Alert, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { formatDateTime } from "../../utils/formatters.js";

export default function BackendForecastChart({ prediction, current }) {
  if (!prediction?.horizons?.length) return <Alert type="info" showIcon title="此站預測暫時不可用"
    description={prediction?.reason || "預測資料尚未提供"} />;
  const horizons = prediction.horizons;
  const option = {
    backgroundColor: "transparent", textStyle: { color: "#cbd5e1" },
    tooltip: { trigger: "axis" }, legend: { textStyle: { color: "#cbd5e1" } },
    grid: { left: 42, right: 15, top: 35, bottom: 35 },
    xAxis: { type: "category", data: ["觀測", ...horizons.map(h => `+${h.horizon_minutes} 分`)] },
    yAxis: { type: "value", name: "可借車輛", min: 0, max: current.total_docks },
    series: [
      { name: "區間下界", type: "line", data: [null, ...horizons.map(h => h.lower_bound)], lineStyle: { type: "dashed" } },
      { name: "點估計", type: "line", data: [current.available_bikes, ...horizons.map(h => h.predicted_available)], itemStyle: { color: "#38d9a9" } },
      { name: "區間上界", type: "line", data: [null, ...horizons.map(h => h.upper_bound)], lineStyle: { type: "dashed" } },
    ],
  };
  return <div>
    <Typography.Title level={5}>未來存量預測 · {prediction.source}</Typography.Title>
    <Typography.Text type="secondary">起算：{formatDateTime(prediction.predict_from)}</Typography.Text>
    {prediction.status === "degraded" && <Alert type="warning" showIcon title="部分預測特徵缺失"
      description={`缺少 ${prediction.missing_features?.length || 0} 項特徵，請搭配現況判讀。`} />}
    <ReactECharts option={option} style={{ height: 250 }} />
  </div>;
}
