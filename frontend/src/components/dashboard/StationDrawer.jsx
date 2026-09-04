import { Alert, Descriptions, Drawer, Empty, Spin, Tag, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { formatDateTime, stationStatusLabels } from "../../utils/formatters.js";

const AXIS_COLOR = "#8ea0b5";
const GRID_COLOR = "rgba(148,163,184,0.15)";

function historyOption(history) {
  return {
    backgroundColor: "transparent",
    textStyle: { color: "#cbd5e1" },
    grid: { left: 40, right: 20, top: 34, bottom: 30 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0e1626",
      borderColor: "#243149",
      textStyle: { color: "#e5ecf5" },
    },
    legend: { data: ["可借車輛", "緊急度"], textStyle: { color: AXIS_COLOR } },
    xAxis: {
      type: "category",
      data: history.map((item) => formatDateTime(item.timestamp)),
      axisLine: { lineStyle: { color: GRID_COLOR } },
      axisLabel: { color: AXIS_COLOR },
    },
    yAxis: [
      {
        type: "value",
        name: "台",
        nameTextStyle: { color: AXIS_COLOR },
        axisLabel: { color: AXIS_COLOR },
        splitLine: { lineStyle: { color: GRID_COLOR } },
      },
      {
        type: "value",
        name: "分",
        max: 100,
        nameTextStyle: { color: AXIS_COLOR },
        axisLabel: { color: AXIS_COLOR },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "可借車輛",
        type: "line",
        smooth: true,
        data: history.map((item) => item.available_bikes),
        itemStyle: { color: "#38d9a9" },
        areaStyle: { color: "rgba(56,217,169,0.12)" },
      },
      {
        name: "緊急度",
        type: "line",
        yAxisIndex: 1,
        data: history.map((item) => item.urgency_score),
        itemStyle: { color: "#ffa94d" },
      },
    ],
  };
}

// 用既有 prediction 的 lower/upper/predicted（Dispatch ETA 區間）畫信賴區間範圍條。
// 缺任一數值即不渲染，交由外層顯示「不可用」，不插值或捏造。
function ForecastIntervalBar({ prediction, capacity }) {
  const lower = Number(prediction?.lower_bound);
  const upper = Number(prediction?.upper_bound);
  const predicted = Number(prediction?.predicted_available);
  const max = Number(capacity);
  if (![lower, upper, predicted, max].every(Number.isFinite) || max <= 0) {
    return null;
  }

  const pct = (value) => `${Math.min(100, Math.max(0, (value / max) * 100))}%`;
  const bandLeft = pct(Math.min(lower, upper));
  const bandWidth = `${Math.min(100, Math.max(0, (Math.abs(upper - lower) / max) * 100))}%`;

  return (
    <div className="forecast-ci">
      <div className="forecast-ci-head">
        <Typography.Text type="secondary">預測信賴區間（可借車輛）</Typography.Text>
        <span className="mono forecast-ci-range">
          {lower}–{upper} 台｜點估計 {predicted}
        </span>
      </div>
      <div className="forecast-ci-track">
        <div className="forecast-ci-band" style={{ left: bandLeft, width: bandWidth }} />
        <div className="forecast-ci-point" style={{ left: pct(predicted) }} />
      </div>
      <div className="forecast-ci-scale mono">
        <span>0</span>
        <span>容量 {max}</span>
      </div>
    </div>
  );
}

export default function StationDrawer({ open, onClose, detail, loading, error }) {
  const current = detail?.current;

  return (
    <Drawer
      title={current?.station_name || "站點詳情"}
      width={520}
      open={open}
      onClose={onClose}
    >
      {loading ? <Spin /> : null}
      {error ? <Alert type="error" showIcon message={error.message} /> : null}
      {!loading && !error && current ? (
        <div className="drawer-stack">
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="行政區">{current.district}</Descriptions.Item>
            <Descriptions.Item label="狀態">
              <Tag>{stationStatusLabels[current.status] || current.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="可借">{current.available_bikes} 台</Descriptions.Item>
            <Descriptions.Item label="可還">{current.available_docks} 位</Descriptions.Item>
            <Descriptions.Item label="使用率">{current.usage_rate}%</Descriptions.Item>
            <Descriptions.Item label="資料時間">{formatDateTime(current.timestamp)}</Descriptions.Item>
          </Descriptions>

          {detail.prediction ? (
            <div className="drawer-stack">
              <Alert
                type="warning"
                showIcon
                message={`Dispatch ETA（${detail.prediction.horizon_minutes} 分鐘）預測 ${detail.prediction.predicted_available} 台`}
                description={`這是既有動態到達時間預測，不是固定 +30／+60 展示。決策應由規則引擎依區間下界判斷。`}
              />
              <ForecastIntervalBar
                prediction={detail.prediction}
                capacity={current.total_docks}
              />
            </div>
          ) : (
            <Alert type="info" showIcon message="此站目前沒有 Mock 預測明細" />
          )}

          <div>
            <Typography.Title level={5}>站點歷史</Typography.Title>
            {detail.history?.length ? (
              <ReactECharts option={historyOption(detail.history)} style={{ height: 260 }} />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="此站沒有歷史 Mock" />
            )}
          </div>
        </div>
      ) : null}
    </Drawer>
  );
}
