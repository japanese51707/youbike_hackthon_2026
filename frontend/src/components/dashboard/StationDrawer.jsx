import { Alert, Descriptions, Drawer, Empty, Spin, Tag, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import {
  areaTypeLabels,
  formatDateTime,
  freshnessLabels,
  stationStatusLabels,
} from "../../utils/formatters.js";
import {
  computeElevationVsNeighbors,
  deriveCapacityTier,
  deriveStationTags,
  deriveTidalPattern,
  getStationElevation,
  PENDING_DATA_SOURCES,
} from "../../config/stationEnrichment.js";
import StationForecastChart from "./StationForecastChart.jsx";

const weatherConditionLabels = {
  clear: "晴",
  cloudy: "多雲",
  rain: "雨",
  heavy_rain: "大雨",
  thunderstorm: "雷雨",
};

// 區域天氣：mock 只有單一行政區的天氣，只有同區站點才顯示為該站參考天氣，
// 其他區明確標示「無此區即時天氣 Mock」，不套用不相符的資料。
function StationWeather({ station, weather }) {
  if (!weather) return null;
  const sameDistrict = station.district === weather.district;

  if (!sameDistrict) {
    return (
      <Alert
        type="info"
        showIcon
        message="即時天氣"
        description={`目前 Mock 僅提供「${weather.district}」的即時天氣，此站所屬「${station.district}」無對應資料。`}
      />
    );
  }

  return (
    <Descriptions
      title={`即時天氣（${weather.district}）`}
      column={2}
      size="small"
      bordered
    >
      <Descriptions.Item label="天氣">
        {weatherConditionLabels[weather.condition] ?? weather.condition}
      </Descriptions.Item>
      <Descriptions.Item label="氣溫">
        <span className="mono">{weather.temperature}°C</span>
      </Descriptions.Item>
      <Descriptions.Item label="降雨機率">
        <span className="mono">{weather.rain_probability}%</span>
      </Descriptions.Item>
      <Descriptions.Item label="資料時間">
        {formatDateTime(weather.timestamp)}
      </Descriptions.Item>
      <Descriptions.Item label="說明" span={2}>
        {weather.description}
      </Descriptions.Item>
    </Descriptions>
  );
}

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

export default function StationDrawer({ open, onClose, detail, loading, error, weather }) {
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
          {/* 即時狀態 */}
          <Descriptions title="即時狀態" column={2} size="small" bordered>
            <Descriptions.Item label="狀態">
              <Tag>{stationStatusLabels[current.status] || current.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="服務狀態">
              {current.service_available ? (
                <Tag color="green">正常營運</Tag>
              ) : (
                <Tag color="red">暫停服務</Tag>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="可借">
              <span className="mono">{current.available_bikes}</span> 台
            </Descriptions.Item>
            <Descriptions.Item label="可還">
              <span className="mono">{current.available_docks}</span> 位
            </Descriptions.Item>
            <Descriptions.Item label="容量">
              <span className="mono">{current.total_docks}</span> 格
            </Descriptions.Item>
            <Descriptions.Item label="使用率">
              <span className="mono">{current.usage_rate}%</span>
            </Descriptions.Item>
            <Descriptions.Item label="資料新鮮度">
              {freshnessLabels[current.data_freshness] ?? current.data_freshness ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="資料時間">
              {formatDateTime(current.timestamp)}
            </Descriptions.Item>
          </Descriptions>

          {/* 站點特徵 */}
          <Descriptions title="站點特徵" column={2} size="small" bordered>
            <Descriptions.Item label="行政區">{current.district}</Descriptions.Item>
            <Descriptions.Item label="區域類型">
              {areaTypeLabels[current.area_type] ?? current.area_type ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="容量規模">
              {deriveCapacityTier(current) ?? "—"}
            </Descriptions.Item>
            <Descriptions.Item label="潮汐型態（推斷）">
              {deriveTidalPattern(current)}
            </Descriptions.Item>
          </Descriptions>

          <div className="station-tags">
            {deriveStationTags(current).map((tag) => (
              <Tag key={tag} color="cyan">
                {tag}
              </Tag>
            ))}
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
              特徵依站名自動標註
            </Typography.Text>
          </div>

          {/* 地理與流動 */}
          <Descriptions title="地理與流動" column={2} size="small" bordered>
            <Descriptions.Item label="海拔（範例）">
              {getStationElevation(current) != null ? (
                <span className="mono">{getStationElevation(current)} m</span>
              ) : (
                "—"
              )}
            </Descriptions.Item>
            <Descriptions.Item label="鄰站相對高度">
              {(() => {
                const rel = computeElevationVsNeighbors(
                  current,
                  detail.params?.params?.nearby_stations,
                );
                if (!rel) return "—";
                const sign = rel.diff > 0 ? "+" : "";
                return (
                  <span>
                    <span className="mono">
                      {sign}
                      {rel.diff} m
                    </span>
                    ｜{rel.tendency}
                  </span>
                );
              })()}
            </Descriptions.Item>
          </Descriptions>

          {/* 環境 */}
          <StationWeather station={current} weather={weather} />

          {/* 未來預測（固定 +30／+60 展示曲線） */}
          <StationForecastChart stationId={current.station_id} />

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

          <Alert
            type="info"
            showIcon
            message="待接真實資料源"
            description={
              <span>
                以下屬性目前為範例／推斷或尚未提供，將由真實資料源取代：
                {PENDING_DATA_SOURCES.join("、")}。
              </span>
            }
          />
        </div>
      ) : null}
    </Drawer>
  );
}
