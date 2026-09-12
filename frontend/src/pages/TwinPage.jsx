import { QuestionCircleOutlined } from "@ant-design/icons";
import { Checkbox, Popover, Segmented, Tag, Typography } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import StationDrawer from "../components/dashboard/StationDrawer.jsx";
import StationLegend from "../components/map/StationLegend.jsx";
import SharedMap from "../components/map/SharedMap.jsx";
import {
  createFlowArcLayer,
  createGiStarVoronoiLayer,
  createKdeHeatmapLayer,
  createNetworkLayers,
} from "../components/map/layers/analysisLayers.js";
import { createDensityLayer } from "../components/map/layers/densityLayer.js";
import { createStationGaugeLayer } from "../components/map/layers/stationGaugeLayer.js";
import { isApiMode, request } from "../api/httpClient.js";
import { loadTemporalPresentation } from "../api/temporalMockAdapter.js";
import { createDistrictOutlineLayer } from "../components/map/layers/districtOutlineLayer.js";
import TwinAgentPane from "../components/twin/TwinAgentPane.jsx";
import TwinAssistant from "../components/twin/TwinAssistant.jsx";
import TwinDistrictCard from "../components/twin/TwinDistrictCard.jsx";
import TwinInsightPanel from "../components/twin/TwinInsightPanel.jsx";
import TwinLayerExplain from "../components/twin/TwinLayerExplain.jsx";
import TwinOptimizationPane from "../components/twin/TwinOptimizationPane.jsx";
import { ANALYSIS_CATALOG, PENDING_ANALYSES } from "../config/analysisCatalog.js";
import presentationConfig from "../config/presentation.json";
import districtCatalog from "../data/newtaipeiDistricts.json";
import useDashboardData from "../hooks/useDashboardData.js";
import {
  CITY_SCOPE,
  countScopedCoverage,
  districtOutline,
  filterByDistrict,
  isCityScope,
  listDistricts,
  outlineBounds,
} from "../utils/districtScope.js";
import { stationStatusLabels } from "../utils/formatters.js";
import { getStationColor } from "../utils/mapPresentation.js";
import { GI_STAR_RAMP } from "../utils/spatialStats.js";
import { resolveTwinFlowRecommendations } from "../utils/twinFlowMock.js";
import { buildHeadline, buildTwinInsights, pickObservedAt } from "../utils/twinInsights.js";
import { buildTwinView, pickTimelineFrame } from "../utils/twinSnapshot.js";

const ALL_LAYER_KEYS = ANALYSIS_CATALOG.map((item) => item.key);

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

const GI_RAMP_CSS = GI_STAR_RAMP.map(([, color]) => `rgb(${color.join(",")})`).join(", ");

export default function TwinPage() {
  const dashboard = useDashboardData({ lite: true });
  const [searchParams, setSearchParams] = useSearchParams();
  const [active, setActive] = useState(["gauge", "voronoi"]);
  const [mode, setMode] = useState("live");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [timeline, setTimeline] = useState(null);
  const [timelineNote, setTimelineNote] = useState("");
  const [agentOpen, setAgentOpen] = useState(true);
  const [district, setDistrict] = useState(CITY_SCOPE);
  const [focusTarget, setFocusTarget] = useState(null);
  const skipInitialCityFocus = useRef(true);
  const [reviewStationIds, setReviewStationIds] = useState([]);
  const agentTab = searchParams.get("tab") === "optimization" ? "optimization" : "assistant";
  const setAgentTab = useCallback(
    (tab) => {
      setSearchParams(tab === "optimization" ? { tab: "optimization" } : {}, { replace: true });
    },
    [setSearchParams],
  );
  const highlightReview = useCallback((ids) => setReviewStationIds(ids ?? []), []);
  const reviewIdSet = useMemo(() => new Set(reviewStationIds), [reviewStationIds]);
  const pinSize = useCallback(
    (station) => (reviewIdSet.has(station.station_id) ? 48 : 36),
    [reviewIdSet],
  );

  const temporal = useMemo(() => {
    try {
      return loadTemporalPresentation();
    } catch {
      return null;
    }
  }, []);

  useEffect(() => {
    if (!isApiMode || mode !== "past") {
      setTimelineNote("");
      return undefined;
    }
    let activeRequest = true;
    request("/stations/timeline?district=全市&date=2026-06-02")
      .then((payload) => {
        if (activeRequest) {
          setTimeline(payload);
          setTimelineNote(payload?.note || "");
        }
      })
      .catch((error) => {
        if (activeRequest) {
          setTimeline(null);
          setTimelineNote(error.message || "全市歷史快照尚未提供");
        }
      });
    return () => {
      activeRequest = false;
    };
  }, [mode]);

  const stations = dashboard.data?.stations ?? [];
  const historyFrame = mode === "past" ? pickTimelineFrame(timeline) : null;
  const temporalView = useMemo(
    () =>
      buildTwinView({
        stations,
        mode,
        temporalStations: temporal?.stations,
        historyFrame,
        recommendations: dashboard.data?.recommendations,
      }),
    [stations, mode, temporal, historyFrame, dashboard.data?.recommendations],
  );
  const snapshot = temporalView.stations;
  const districts = useMemo(() => listDistricts(stations), [stations]);
  const scopedSnapshot = useMemo(() => filterByDistrict(snapshot, district), [snapshot, district]);
  const scopedLive = useMemo(() => filterByDistrict(stations, district), [stations, district]);
  const scopedRecommendations = useMemo(
    () => filterByDistrict(dashboard.data?.recommendations, district),
    [dashboard.data?.recommendations, district],
  );
  const flowView = useMemo(
    () =>
      resolveTwinFlowRecommendations({
        stations: scopedSnapshot,
        recommendations: scopedRecommendations,
      }),
    [scopedSnapshot, scopedRecommendations],
  );
  const outline = useMemo(
    () => districtOutline(district, scopedSnapshot, districtCatalog.polygons),
    [district, scopedSnapshot],
  );
  const scopedCoverage = useMemo(() => {
    if (isCityScope(district)) {
      return { covered: temporalView.covered, available: temporalView.available };
    }
    return countScopedCoverage({
      stations: scopedSnapshot,
      mode,
      historyFrame,
      temporalStations: temporal?.stations,
      recommendations: scopedRecommendations,
    });
  }, [district, temporalView, scopedSnapshot, mode, historyFrame, temporal, scopedRecommendations]);
  const scopeLabel = isCityScope(district) ? "全市" : district;

  useEffect(() => {
    if (isCityScope(district)) {
      if (skipInitialCityFocus.current) {
        skipInitialCityFocus.current = false;
        return;
      }
      setFocusTarget({
        id: "district-city",
        longitude: presentationConfig.maps.dashboard.longitude,
        latitude: presentationConfig.maps.dashboard.latitude,
        zoom: presentationConfig.maps.dashboard.zoom,
      });
      return;
    }
    skipInitialCityFocus.current = false;
    const next = districtOutline(district, [], districtCatalog.polygons);
    const bounds = outlineBounds(next?.polygons);
    if (!bounds) return;
    setFocusTarget({
      id: `district-${district}`,
      bounds,
      padding: { top: 72, bottom: 96, left: 72, right: 380 },
    });
  }, [district]);

  const fullInsightReport = useMemo(
    () =>
      buildTwinInsights({
        stations: scopedSnapshot,
        liveStations: scopedLive,
        recommendations: flowView.recommendations,
        flowPairs: flowView.pairs,
        activeLayers: ALL_LAYER_KEYS,
        mode,
        temporalCovered: scopedCoverage.covered,
        temporalAvailable: scopedCoverage.available,
        stationsSource: dashboard.data?.stationsSource || (dashboard.loading ? "loading" : "unknown"),
        observedAt: pickObservedAt(scopedSnapshot),
        scopeLabel,
        flowSource: flowView.source,
      }),
    [scopedSnapshot, scopedLive, flowView, mode, scopedCoverage, dashboard.data, dashboard.loading, scopeLabel],
  );
  const insightReport = useMemo(() => {
    const layers = fullInsightReport.layers.filter((layer) => active.includes(layer.key));
    return {
      ...fullInsightReport,
      layers,
      headline: fullInsightReport.cityWideOk ? buildHeadline(layers, fullInsightReport.comparison) : null,
    };
  }, [fullInsightReport, active]);

  const layerModeByKey = useMemo(
    () => new Map(fullInsightReport.layers.map((layer) => [layer.key, layer.dataMode])),
    [fullInsightReport],
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
    const outlineLayer = createDistrictOutlineLayer(outline);
    if (outlineLayer) composed.push(outlineLayer);
    if (on("density")) composed.push(createDensityLayer({ id: "twin-density", data: scopedSnapshot }));
    if (on("kde")) composed.push(createKdeHeatmapLayer({ data: scopedSnapshot }));
    if (on("voronoi")) composed.push(createGiStarVoronoiLayer({ data: scopedSnapshot }));
    if (on("flow")) composed.push(createFlowArcLayer({ pairs: flowView.pairs }));
    if (on("network")) composed.push(...createNetworkLayers({ data: scopedSnapshot, onSelectStation: openStation }));
    if (on("gauge")) {
      composed.push(
        createStationGaugeLayer({
          id: "twin-gauge",
          data: scopedSnapshot,
          dimension: "status",
          getColor,
          onSelectStation: openStation,
          sizePixels: pinSize,
        }),
      );
    }
    return composed.filter(Boolean);
  }, [active, scopedSnapshot, flowView, openStation, pinSize, outline]);

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
            const tag = DATA_MODE_TAG[layerModeByKey.get(item.key) ?? item.dataMode];
            return (
              <div key={item.key} className="twin-layer-row">
                <Checkbox checked={active.includes(item.key)} onChange={() => toggle(item.key)}>
                  {item.name}
                </Checkbox>
                <span className="twin-layer-right">
                  <Tag color={tag.color} className="twin-mode-tag">{tag.text}</Tag>
                  <Popover
                    title={<span>{item.name}<Typography.Text type="secondary" style={{ marginLeft: 6, fontSize: 11 }}>{item.discipline}</Typography.Text></span>}
                    content={<TwinLayerExplain item={item} />}
                    trigger="click"
                  >
                    <QuestionCircleOutlined className="twin-info" />
                  </Popover>
                </span>
              </div>
            );
          })}
        </div>

        {active.includes("voronoi") ? (
          <div className="twin-legend">
            <div className="twin-legend-title">Gi* z 值（鄰近壓力）</div>
            <div className="twin-legend-ramp" style={{ background: `linear-gradient(90deg, ${GI_RAMP_CSS})` }} />
            <div className="twin-legend-ramp-labels">
              <span>冷點</span>
              <span>接近平均</span>
              <span>熱點</span>
            </div>
            <div className="twin-legend-note">顏色依 z 連續漸層；|z|≥1.96 才算顯著，見右側解讀。</div>
          </div>
        ) : null}

        {active.includes("network") ? (
          <div className="twin-legend">
            <div className="twin-legend-title">中心性（圓圈大小＋顏色）</div>
            <div
              className="twin-legend-ramp"
              style={{
                background: `linear-gradient(90deg, ${presentationConfig.layers.centralityColorRange
                  .map((color) => `rgb(${color.join(",")})`)
                  .join(", ")})`,
              }}
            />
            <div className="twin-legend-ramp-labels">
              <span>邊陲</span>
              <span>中等</span>
              <span>樞紐</span>
            </div>
            <div className="twin-legend-note">越大越暖＝地理鄰近中心性越高；不是流量。</div>
          </div>
        ) : null}

        {active.includes("flow") ? (
          <div className="twin-legend">
            <div className="twin-legend-title">流向顏色＝方向</div>
            <div
              className="twin-legend-ramp"
              style={{
                background: `linear-gradient(90deg, rgb(${presentationConfig.layers.arcSourceRgb.join(",")}), rgb(${presentationConfig.layers.arcTargetRgb.join(",")}))`,
              }}
            />
            <div className="twin-legend-ramp-labels">
              <span>橘／取車（偏滿）</span>
              <span>綠／補車（偏空）</span>
            </div>
            <div className="twin-legend-note">顏色只表示從哪裡取、補到哪，不是流量；粗細才是示意量。</div>
          </div>
        ) : null}

        {active.includes("density") ? (
          <div className="twin-legend">
            <div className="twin-legend-title">Hexagon 顏色＝平均使用率</div>
            <div
              className="twin-legend-ramp"
              style={{
                background: `linear-gradient(90deg, ${presentationConfig.layers.hexagonColorRange
                  .map((color) => `rgb(${color.join(",")})`)
                  .join(", ")})`,
              }}
            />
            <div className="twin-legend-ramp-labels">
              <span>空／藍</span>
              <span>約五成</span>
              <span>滿／紅</span>
            </div>
            <div className="twin-legend-note">柱高仍是格內車柱總數；顏色不是流量。</div>
          </div>
        ) : null}

        <StationLegend />
        <Popover
          trigger="click"
          title="待接真實資料源"
          content={<ul style={{ margin: 0, paddingLeft: 16, maxWidth: 260, fontSize: 12 }}>{PENDING_ANALYSES.map((p) => <li key={p}>{p}</li>)}</ul>}
        >
          <div className="twin-pending">＋ 待接真實資料的進階分析</div>
        </Popover>
      </div>

      <TwinDistrictCard
        value={district}
        districts={districts}
        stationCount={scopedSnapshot.length}
        outlineSource={outline?.source}
        onChange={setDistrict}
      />

      <div className="twin-timebar">
        <span className="twin-timebar-label">時間機器</span>
        <Segmented value={mode} options={MODE_OPTIONS} onChange={setMode} />
        <Typography.Text type="secondary" className="twin-timebar-note">
          {mode === "live"
            ? `即時站況可做${scopeLabel}解讀`
            : insightReport.cityWideOk
              ? `${mode === "past" ? "歷史" : "預測"}覆蓋 ${scopedCoverage.covered}/${scopedSnapshot.length} 站，已開${scopeLabel}解讀`
              : `${timelineNote || `僅 ${scopedCoverage.covered}/${scopedSnapshot.length || scopedCoverage.available} 站有樣本`}，${scopeLabel}結論已關閉`}
        </Typography.Text>
      </div>

      <TwinInsightPanel
        report={insightReport}
        loading={dashboard.loading}
        error={dashboard.error}
        onSelectStation={openStation}
      />
    </>
  );

  return (
    <div className="fixed-page twin-page">
      <div className="twin-stage">
        <SharedMap
          ariaLabel="數位孿生戰情室分析地圖"
          className="map-fill"
          initialViewState={presentationConfig.maps.dashboard}
          focusTarget={focusTarget}
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
      <TwinAgentPane
        open={agentOpen}
        onOpenChange={setAgentOpen}
        tab={agentTab}
        onTabChange={setAgentTab}
      >
        <div className="twin-agent-panel" hidden={agentTab !== "assistant"}>
          <TwinAssistant
            report={fullInsightReport}
            snapshot={scopedSnapshot}
            visibleLayers={active}
            dataReady={!dashboard.loading && Boolean(dashboard.data || dashboard.error)}
          />
        </div>
        <div className="twin-agent-panel" hidden={agentTab !== "optimization"}>
          <TwinOptimizationPane onSelectStation={openStation} onHighlightStations={highlightReview} />
        </div>
      </TwinAgentPane>
    </div>
  );
}
