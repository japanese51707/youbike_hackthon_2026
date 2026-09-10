import { QuestionCircleOutlined } from "@ant-design/icons";
import { Checkbox, Popover, Segmented, Slider, Tag, Typography } from "antd";
import { useCallback, useMemo, useState } from "react";
import StationDrawer from "../components/dashboard/StationDrawer.jsx";
import SharedMap from "../components/map/SharedMap.jsx";
import {
  createCatchmentLayer,
  createCoverageGapLayer,
  createFlowArcLayer,
  createGiStarVoronoiLayer,
  createKdeHeatmapLayer,
  createNetworkLayers,
} from "../components/map/layers/analysisLayers.js";
import { createDensityLayer } from "../components/map/layers/densityLayer.js";
import { createStationGaugeLayer } from "../components/map/layers/stationGaugeLayer.js";
import { loadTemporalPresentation } from "../api/temporalMockAdapter.js";
import { ANALYSIS_CATALOG, PENDING_ANALYSES } from "../config/analysisCatalog.js";
import presentationConfig from "../config/presentation.json";
import useDashboardData from "../hooks/useDashboardData.js";
import { stationStatusLabels } from "../utils/formatters.js";
import { getStationColor } from "../utils/mapPresentation.js";
import { giStarClass } from "../utils/spatialStats.js";

const MODE_OPTIONS = [
  { value: "past", label: "歷史" },
  { value: "live", label: "即時" },
  { value: "predict", label: "預測" },
];

const DATA_MODE_TAG = {
  real: { color: "green", text: "實算" },
  method: { color: "gold", text: "方法展示" },
  pending: { color: "default", text: "待接資料" },
};

const GI_LEGEND = [2.58, 1.96, 0, -1.96, -2.58].map((z) => giStarClass(z));

function statusFromUsage(bikes, docks, usage) {
  if (bikes <= 0) return "empty";
  if (docks <= 0) return "full";
  if (usage < 30) return "low";
  if (usage > 70) return "high";
  return "normal";
}

// 依 Past/Live/Predict 產生站點快照（僅有 temporal mock 的站會改變，其餘維持即時）
function applyTemporal(stations, temporalStations, mode) {
  if (mode === "live" || !temporalStations) return stations;
  const byId = new Map(temporalStations.map((t) => [t.stationId, t]));
  return stations.map((s) => {
    const t = byId.get(s.station_id);
    if (!t) return s;
    let bikes = s.available_bikes;
    if (mode === "past") bikes = t.past.at(-1)?.availableBikes ?? bikes;
    if (mode === "predict") {
      const f =
        t.forecasts.find((x) => x.offsetMinutes === 60 && x.isAvailable) ||
        t.forecasts.find((x) => x.isAvailable);
      bikes = f?.availableBikes ?? bikes;
    }
    const cap = Number(s.total_docks) || 0;
    const docks = Math.max(0, cap - bikes);
    const usage = cap ? Math.round((bikes / cap) * 1000) / 10 : s.usage_rate;
    return { ...s, available_bikes: bikes, available_docks: docks, usage_rate: usage, status: statusFromUsage(bikes, docks, usage) };
  });
}

export default function TwinPage() {
  const dashboard = useDashboardData();
  const [active, setActive] = useState(["gauge", "voronoi"]);
  const [mode, setMode] = useState("live");
  const [catchmentKm, setCatchmentKm] = useState(0.6);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const temporal = useMemo(() => {
    try {
      return loadTemporalPresentation();
    } catch {
      return null;
    }
  }, []);

  const stations = dashboard.data?.stations ?? [];
  const snapshot = useMemo(
    () => applyTemporal(stations, temporal?.stations, mode),
    [stations, temporal, mode],
  );

  const openStation = useCallback(
    (stationId) => {
      dashboard.selectStation(stationId);
      setDrawerOpen(true);
    },
    [dashboard],
  );

  const layers = useMemo(() => {
    const on = (k) => active.includes(k);
    const getColor = (s) => getStationColor(s, "status");
    const composed = [];
    if (on("density")) composed.push(createDensityLayer({ id: "twin-density", data: snapshot }));
    if (on("coverage")) composed.push(createCoverageGapLayer({ data: snapshot }));
    if (on("kde")) composed.push(createKdeHeatmapLayer({ data: snapshot }));
    if (on("catchment")) composed.push(createCatchmentLayer({ data: snapshot, radiusKm: catchmentKm }));
    if (on("voronoi")) composed.push(createGiStarVoronoiLayer({ data: snapshot }));
    if (on("flow")) composed.push(createFlowArcLayer({ recommendations: dashboard.data?.recommendations }));
    if (on("network")) composed.push(...createNetworkLayers({ data: snapshot, onSelectStation: openStation }));
    if (on("gauge")) {
      composed.push(
        createStationGaugeLayer({ id: "twin-gauge", data: snapshot, dimension: "status", getColor, onSelectStation: openStation }),
      );
    }
    return composed.filter(Boolean);
  }, [active, snapshot, catchmentKm, dashboard.data, openStation]);

  const getTooltip = useCallback(({ object }) => {
    if (!object?.station_name) return null;
    return {
      text: `${object.station_name}\n${stationStatusLabels[object.status] ?? object.status}｜可借 ${object.available_bikes}／可還 ${object.available_docks}`,
    };
  }, []);

  const toggle = (key) =>
    setActive((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));

  const overlay = (
    <>
      <div className="twin-control">
        <div className="twin-control-title">分析圖層</div>
        <div className="twin-layer-list">
          {ANALYSIS_CATALOG.map((item) => {
            const tag = DATA_MODE_TAG[item.dataMode];
            return (
              <div key={item.key} className="twin-layer-row">
                <Checkbox checked={active.includes(item.key)} onChange={() => toggle(item.key)}>
                  {item.name}
                </Checkbox>
                <span className="twin-layer-right">
                  <Tag color={tag.color} className="twin-mode-tag">{tag.text}</Tag>
                  <Popover
                    title={<span>{item.name}<Typography.Text type="secondary" style={{ marginLeft: 6, fontSize: 11 }}>{item.discipline}</Typography.Text></span>}
                    content={<div style={{ maxWidth: 260, fontSize: 12 }}>{item.info}</div>}
                    trigger="click"
                  >
                    <QuestionCircleOutlined className="twin-info" />
                  </Popover>
                </span>
              </div>
            );
          })}
        </div>

        {active.includes("catchment") ? (
          <div className="twin-slider">
            <span>服務半徑</span>
            <Slider min={0.2} max={2} step={0.1} value={catchmentKm} onChange={setCatchmentKm} style={{ flex: 1 }} tooltip={{ formatter: (v) => `${v} km` }} />
            <Tag className="mono">{catchmentKm} km</Tag>
          </div>
        ) : null}

        {active.includes("voronoi") ? (
          <div className="twin-legend">
            <div className="twin-legend-title">Gi* 熱點顯著性</div>
            {GI_LEGEND.map((c) => (
              <span key={c.key} className="twin-legend-item">
                <span className="twin-legend-dot" style={{ background: `rgb(${c.color.join(",")})` }} />
                {c.label}
              </span>
            ))}
          </div>
        ) : null}

        <Popover
          trigger="click"
          title="待接真實資料源"
          content={<ul style={{ margin: 0, paddingLeft: 16, maxWidth: 260, fontSize: 12 }}>{PENDING_ANALYSES.map((p) => <li key={p}>{p}</li>)}</ul>}
        >
          <div className="twin-pending">＋ 待接真實資料的進階分析</div>
        </Popover>
      </div>

      <div className="twin-timebar">
        <span className="twin-timebar-label">時間機器</span>
        <Segmented value={mode} options={MODE_OPTIONS} onChange={setMode} />
        <Typography.Text type="secondary" className="twin-timebar-note">
          {mode === "live" ? "即時站況" : "僅少數站有歷史/預測 Mock，其餘顯示即時"}
        </Typography.Text>
      </div>
    </>
  );

  return (
    <div className="fixed-page twin-page">
      <SharedMap
        ariaLabel="數位孿生戰情室分析地圖"
        className="map-fill"
        initialViewState={presentationConfig.maps.dashboard}
        layers={layers}
        getTooltip={getTooltip}
        overlay={overlay}
      />
      <StationDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        detail={dashboard.detail}
        loading={dashboard.detailLoading}
        error={dashboard.detailError}
        weather={dashboard.data?.weather}
      />
    </div>
  );
}
