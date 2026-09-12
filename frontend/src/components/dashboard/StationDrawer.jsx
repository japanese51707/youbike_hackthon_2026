import { InfoCircleOutlined } from "@ant-design/icons";
import { useAppearance } from "../../theme/ThemeProvider.jsx";
import { Alert, Descriptions, Drawer, Empty, Spin, Tabs, Tag, Tooltip, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { useEffect, useState } from "react";
import {
  areaTypeLabels,
  formatDateTime,
  formatStationTime,
  freshnessLabels,
  stationStatusLabels,
} from "../../utils/formatters.js";
import {
  deriveCapacityTier,
  deriveStationTags,
  deriveTidalPattern,
} from "../../config/stationEnrichment.js";
import { getStationEnrichment } from "../../api/stationsApi.js";
import { isApiMode } from "../../api/httpClient.js";
import StationForecastChart from "./StationForecastChart.jsx";

const terrainClassLabels = {
  flat: "平地",
  gentle: "緩坡",
  moderate: "中坡",
  steep: "陡坡",
};

// 單站即時天氣（CWA）：後端 /weather/by-location 依沃羅諾伊最近測站對應——
// 最近「雨量站」給即時雨量、最近「氣象站」給溫度/濕度/風速。兩者可能是不同測站，各自標距離。
function StationWeather({ weather }) {
  if (!weather) {
    return (
      <Alert
        type="info"
        showIcon
        message="即時天氣"
        description="此站即時天氣暫不可用（CWA 測站資料取得失敗或本站無座標）。"
      />
    );
  }
  const rain = weather.rainfall || {};
  const wx = weather.weather || {};
  const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : null);

  return (
    <Descriptions
      title="即時天氣（CWA 最近測站）"
      column={2}
      size="small"
      bordered
    >
      <Descriptions.Item label="天氣">{wx.raw_weather || wx.condition || "—"}</Descriptions.Item>
      <Descriptions.Item label="氣溫">
        <span className="mono">
          {num(wx.temperature_c) != null ? `${wx.temperature_c}°C` : "—"}
        </span>
      </Descriptions.Item>
      <Descriptions.Item label="濕度">
        <span className="mono">{num(wx.humidity) != null ? `${wx.humidity}%` : "—"}</span>
      </Descriptions.Item>
      <Descriptions.Item label="風速">
        <span className="mono">
          {num(wx.wind_speed) != null ? `${wx.wind_speed} m/s` : "—"}
        </span>
      </Descriptions.Item>
      <Descriptions.Item label="目前雨量">
        <span className="mono">{num(rain.now) != null ? `${rain.now} mm` : "—"}</span>
      </Descriptions.Item>
      <Descriptions.Item label="近1小時雨量">
        <span className="mono">{num(rain.past1hr) != null ? `${rain.past1hr} mm` : "—"}</span>
      </Descriptions.Item>
      <Descriptions.Item label="雨量測站" span={1}>
        {rain.name ? `${rain.name}（${num(rain.distance_km) ?? "?"} km）` : "—"}
      </Descriptions.Item>
      <Descriptions.Item label="氣象測站" span={1}>
        {wx.name ? `${wx.name}（${num(wx.distance_km) ?? "?"} km）` : "—"}
      </Descriptions.Item>
      <Descriptions.Item label="觀測時間" span={2}>
        {formatDateTime(wx.observed_at || rain.observed_at)}
      </Descriptions.Item>
    </Descriptions>
  );
}


function historyOption(history, colors) {
  return {
    backgroundColor: "transparent",
    textStyle: { color: colors.text },
    grid: { left: 40, right: 20, top: 34, bottom: 30 },
    tooltip: {
      trigger: "axis",
      backgroundColor: colors.panel,
      borderColor: colors.border,
      textStyle: { color: colors.text },
    },
    legend: { data: ["可借車輛", "緊急度"], textStyle: { color: colors.muted } },
    xAxis: {
      type: "category",
      data: history.map((item) => formatDateTime(item.timestamp)),
      axisLine: { lineStyle: { color: colors.grid } },
      axisLabel: { color: colors.muted },
    },
    yAxis: [
      {
        type: "value",
        name: "台",
        nameTextStyle: { color: colors.muted },
        axisLabel: { color: colors.muted },
        splitLine: { lineStyle: { color: colors.grid } },
      },
      {
        type: "value",
        name: "分",
        max: 100,
        nameTextStyle: { color: colors.muted },
        axisLabel: { color: colors.muted },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: "可借車輛",
        type: "line",
        smooth: true,
        data: history.map((item) => item.available_bikes),
        itemStyle: { color: colors.line },
        areaStyle: { color: colors.band },
      },
      {
        name: "緊急度",
        type: "line",
        yAxisIndex: 1,
        data: history.map((item) => item.urgency_score),
        itemStyle: { color: colors.info },
      },
    ],
  };
}

// 站況顏色語意（與地圖/側欄一致）。
const STATUS_META = {
  empty: { color: "var(--ct-danger)", label: "空站" },
  low: { color: "var(--ct-warning)", label: "偏低" },
  normal: { color: "var(--ct-success)", label: "正常" },
  high: { color: "var(--ct-warning)", label: "偏高" },
  full: { color: "var(--ct-danger)", label: "滿站" },
  offline: { color: "var(--ct-text-dim)", label: "離線" },
};

// 即時狀態摘要（第一眼）：狀態徽章 + 可借/可還/使用率大字，資料時間與來源說明收成小字/icon。
function StationNowSummary({ current }) {
  const meta = STATUS_META[current.status] ?? { color: "var(--ct-text)", label: current.status };
  const sourceNote =
    "站況、天氣（CWA 最近測站）、高程（DEM）、預測（LightGBM）皆為真實資料；" +
    "站點特徵標籤與潮汐型態為依站名／區域類型的推斷分類，周邊人流與即時路況尚未接入。";
  return (
    <div className="station-now">
      <div className="station-now-head">
        <Tag color={current.service_available ? undefined : "red"} style={{ borderColor: meta.color, color: meta.color }}>
          {stationStatusLabels[current.status] || meta.label}
        </Tag>
        {!current.service_available ? <Tag color="red">暫停服務</Tag> : null}
        <Tag color="default">{freshnessLabels[current.data_freshness] ?? current.data_freshness ?? "—"}</Tag>
        <Tooltip
          title={
            <span className="mono" style={{ fontSize: 12 }}>
              資料源更新：{current.source_timestamp ? formatStationTime({ source_timestamp: current.source_timestamp }) : "—"}
              <br />
              系統取得：{current.timestamp ? formatStationTime({ timestamp: current.timestamp }) : "—"}
              <br />
              <br />
              {sourceNote}
            </span>
          }
        >
          <InfoCircleOutlined style={{ marginLeft: "auto", color: "var(--ct-text-dim)", cursor: "help" }} />
        </Tooltip>
      </div>
      <div className="station-now-metrics">
        <div className="station-now-metric">
          <span className="station-now-value mono" style={{ color: meta.color }}>
            {current.available_bikes}
          </span>
          <span className="station-now-label">可借（台）</span>
        </div>
        <div className="station-now-metric">
          <span className="station-now-value mono">{current.available_docks}</span>
          <span className="station-now-label">可還（位）</span>
        </div>
        <div className="station-now-metric">
          <span className="station-now-value mono">{current.usage_rate}%</span>
          <span className="station-now-label">使用率</span>
        </div>
        <div className="station-now-metric">
          <span className="station-now-value mono">{current.total_docks}</span>
          <span className="station-now-label">總柱數</span>
        </div>
      </div>
    </div>
  );
}

export default function StationDrawer({ open, onClose, detail, loading, error }) {
  const { colors } = useAppearance();
  const current = detail?.current;

  // 抓單站加值：靜態（真實高程 terrain.elevation）＋ 該站最近測站即時天氣（CWA 沃羅諾伊）。
  const [enrichment, setEnrichment] = useState({ static: null, weather: null });
  const stationId = current?.station_id;
  const lat = current?.lat;
  const lng = current?.lng;
  useEffect(() => {
    if (!open || !isApiMode || !stationId) {
      setEnrichment({ static: null, weather: null });
      return undefined;
    }
    let active = true;
    getStationEnrichment(stationId, { lat, lng })
      .then((r) => {
        if (active) setEnrichment(r);
      })
      .catch(() => {
        if (active) setEnrichment({ static: null, weather: null });
      });
    return () => {
      active = false;
    };
  }, [open, stationId, lat, lng]);

  const terrain = enrichment.static?.terrain;
  const elevation = Number.isFinite(Number(terrain?.elevation)) ? Number(terrain.elevation) : null;

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
          {/* 第一眼：即時狀態摘要（關鍵數字大字）*/}
          <StationNowSummary current={current} />

          {/* 第一眼：未來預測 */}
          <StationForecastChart current={current} prediction={detail.prediction} />

          {/* 參考資料：站點特徵 / 地理 / 天氣 / 歷史，收進 tab 切換 */}
          <Tabs
            className="drawer-ref-tabs"
            size="small"
            items={[
              {
                key: "profile",
                label: "站點特徵",
                children: (
                  <div className="drawer-stack">
                    <Descriptions column={2} size="small" bordered>
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
                  </div>
                ),
              },
              {
                key: "geo",
                label: "地理",
                children: (
                  <Descriptions column={2} size="small" bordered>
                    <Descriptions.Item label="海拔（實測）">
                      {elevation != null ? <span className="mono">{elevation} m</span> : "—"}
                    </Descriptions.Item>
                    <Descriptions.Item label="坡度">
                      {Number.isFinite(Number(terrain?.slope_pct)) ? (
                        <span>
                          <span className="mono">{terrain.slope_pct}%</span>
                          {terrain?.terrain_class
                            ? `｜${terrainClassLabels[terrain.terrain_class] ?? terrain.terrain_class}`
                            : ""}
                        </span>
                      ) : (
                        "—"
                      )}
                    </Descriptions.Item>
                  </Descriptions>
                ),
              },
              {
                key: "weather",
                label: "即時天氣",
                children: <StationWeather weather={enrichment.weather} />,
              },
              {
                key: "history",
                label: "歷史",
                children: detail.history?.length ? (
                  <ReactECharts option={historyOption(detail.history, colors)} style={{ height: 260 }} />
                ) : (
                  <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={
                      detail.history_status?.reason ||
                      "即時資料源不提供歷史序列（歷史查詢需切換 historical 源）"
                    }
                  />
                ),
              },
            ]}
          />
        </div>
      ) : null}
    </Drawer>
  );
}
