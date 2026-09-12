import { Card, Checkbox } from "antd";
import { ScatterplotLayer } from "@deck.gl/layers";
import { useCallback, useMemo, useState } from "react";
import SharedMap from "../map/SharedMap.jsx";
import { createStationGaugeLayer } from "../map/layers/stationGaugeLayer.js";
import { createVoronoiLayer } from "../map/layers/voronoiLayer.js";
import { createDensityLayer } from "../map/layers/densityLayer.js";
import { createPlanRouteLayers } from "../map/layers/planLayers.js";
import presentationConfig from "../../config/presentation.json";
import {
  areaTypeLabels,
  formatStationTime,
} from "../../utils/formatters.js";
import {
  deriveStationTags,
  getStationElevation,
} from "../../config/stationEnrichment.js";
import StationLegend from "../map/StationLegend.jsx";
import { escapeHtml } from "../../utils/escapeHtml.js";
import { getRentalStatus, rentalLabels, hasAvailableElectricBike } from "../../utils/stationAppearance.js";
import { getStationColor } from "../../utils/mapPresentation.js";

const layerOptions = [
  { label: "站點標記", value: "stations" },
  { label: "高負載熱區（Voronoi）", value: "zones" },
  { label: "容量密度基底（Hexagon）", value: "density" },
];


function buildTooltipHtml(station) {
  const capacity = Number(station.total_docks) || 0;
  const bikes = Number(station.available_bikes) || 0;
  const ratio = capacity > 0 ? Math.round((bikes / capacity) * 100) : 0;
  const tone = getStationColor(station);
  const statusLabel = rentalLabels[getRentalStatus(station)];
  const stale = station.data_freshness && station.data_freshness !== "live";
  const elevation = getStationElevation(station);
  const tags = deriveStationTags(station);
  const dataTime = formatStationTime(station);

  return `
    <div style="font-family:'Noto Sans TC',sans-serif;min-width:210px">
      <div style="font-weight:700;font-size:13px;color:var(--ct-text)">${escapeHtml(station.station_name)}</div>
      <div style="font-size:11px;color:var(--ct-text-dim);margin-bottom:8px">${escapeHtml(station.district)}｜${escapeHtml(areaTypeLabels[station.area_type] ?? station.area_type ?? "")}${elevation != null ? `｜海拔 ${elevation}m（範例）` : ""}</div>
      ${tags.length ? `<div style="margin-bottom:6px">${tags.map((t) => `<span style="display:inline-block;font-size:10px;color:var(--ct-info);border:1px solid var(--ct-border);border-radius:4px;padding:1px 5px;margin-right:4px">${escapeHtml(t)}</span>`).join("")}</div><div style="font-size:10px;color:var(--ct-text-dim);margin-bottom:8px">特徵依站名自動標註</div>` : ""}
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${tone}"></span>
        <span style="font-size:12px;color:var(--ct-text)">${statusLabel}</span>
        ${hasAvailableElectricBike(station) ? '<span style="font-size:11px;color:var(--ct-primary)">⚡ YouBike 2.0E</span>' : ""}
        ${station.service_available === false ? '<span style="font-size:10px;color:var(--ct-danger)">暫停服務</span>' : ""}
        ${stale ? '<span style="font-size:10px;color:var(--ct-warning)">資料延遲</span>' : ""}
      </div>
      <div style="height:6px;border-radius:3px;background:var(--ct-border);overflow:hidden">
        <div style="height:100%;width:${ratio}%;background:${tone}"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:var(--ct-text);margin-top:6px">
        <span>可借 ${bikes}</span>
        <span>可還 ${Number(station.available_docks) || 0}</span>
        <span>${ratio}%／${capacity}</span>
      </div>
      <div style="margin-top:6px;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:10px;color:var(--ct-text-dim)">資料時間 ${dataTime}</div>
    </div>
  `;
}

const VEHICLE_COLORS = {
  available: [104, 151, 148],
  standby: [211, 158, 74],
  dispatched: [138, 166, 100],
  maintenance: [131, 137, 126],
};

export default function StationMap({
  stations,
  dimension,
  onSelectStation,
  focus,
  highlightStationId = null,
  showLayerControl = false,
  vehicles = [],
  onSelectVehicle,
  draftRoute = null,
}) {
  const [activeLayers, setActiveLayers] = useState(["stations"]);

  const layers = useMemo(() => {
    const getColor = (station) => getStationColor(station, dimension);
    const composed = [];
    // 由下而上疊：密度基底 → 熱區 → 站點環
    if (activeLayers.includes("density")) {
      composed.push(createDensityLayer({ id: "dashboard-density", data: stations }));
    }
    if (activeLayers.includes("zones")) {
      composed.push(
        createVoronoiLayer({ id: "dashboard-zones", data: stations, getColor }),
      );
    }
    // 選中站高亮：在該站畫一個明顯光環，讓「我點的是哪一個」一眼可見。
    const highlighted = highlightStationId
      ? stations.find((s) => s.station_id === highlightStationId)
      : null;
    if (highlighted && Number.isFinite(Number(highlighted.lat)) && Number.isFinite(Number(highlighted.lng))) {
      composed.push(
        new ScatterplotLayer({
          id: "dashboard-highlight",
          data: [highlighted],
          getPosition: (s) => [Number(s.lng), Number(s.lat)],
          getRadius: 22,
          radiusUnits: "pixels",
          stroked: true,
          filled: false,
          getLineColor: [56, 217, 169, 255],
          getLineWidth: 3,
          lineWidthUnits: "pixels",
          pickable: false,
        }),
      );
    }
    if (activeLayers.includes("stations")) {
      composed.push(
        createStationGaugeLayer({
          id: "dashboard-stations",
          data: stations,
          dimension,
          getColor,
          onSelectStation,
        }),
      );
    }

    // 組單草稿路線（先載後放）疊在站點之上。
    if (draftRoute?.stops?.length) {
      composed.push(
        ...createPlanRouteLayers({
          start: draftRoute.start,
          route: draftRoute.stops,
          geometry: draftRoute.geometry,   // 第2件：實走道路折線（無則自動退直線）
          id: "dispatch-draft",
        }),
      );
    }

    // 調度車位置（mock 示意），可點擊觸發「車找站」。
    const vehiclePoints = (vehicles ?? []).filter(
      (v) =>
        v.current_location &&
        Number.isFinite(Number(v.current_location.lat)) &&
        Number.isFinite(Number(v.current_location.lng)),
    );
    if (vehiclePoints.length) {
      composed.push(
        new ScatterplotLayer({
          id: "dashboard-vehicles",
          data: vehiclePoints,
          pickable: true,
          getPosition: (v) => [
            Number(v.current_location.lng),
            Number(v.current_location.lat),
          ],
          getRadius: 10,
          radiusUnits: "pixels",
          stroked: true,
          getFillColor: (v) => VEHICLE_COLORS[v.status] ?? VEHICLE_COLORS.available,
          getLineColor: [255, 254, 250, 240],
          getLineWidth: 2,
          lineWidthUnits: "pixels",
          onClick: ({ object }) => {
            if (object && onSelectVehicle) onSelectVehicle(object);
          },
        }),
      );
    }

    return composed.filter(Boolean);
  }, [activeLayers, dimension, onSelectStation, stations, vehicles, onSelectVehicle, draftRoute, highlightStationId]);

  const layerControl = showLayerControl ? (
    <div className="map-layer-control">
      <div className="map-layer-control-title">圖層</div>
      <Checkbox.Group
        options={layerOptions}
        value={activeLayers}
        onChange={setActiveLayers}
      />
    </div>
  ) : null;
  const getTooltip = useCallback(({ object }) => {
    if (!object) return null;
    // 調度車標記
    if (object.vehicle_id) {
      const statusText = {
        available: "可調度",
        standby: "總站待命（預備車）",
        dispatched: "出勤中",
        maintenance: "維修中",
      };
      return {
        html: `<div style="font-family:'Noto Sans TC',sans-serif;min-width:150px"><div style="font-weight:700;color:var(--ct-text)">${escapeHtml(object.vehicle_id)}</div><div style="font-size:11px;color:var(--ct-text-dim)">${escapeHtml(statusText[object.status] ?? object.status)}｜載運上限 ${escapeHtml(object.max_capacity)} 台｜${escapeHtml(object.current_district ?? "未分區")}</div><div style="font-size:10px;color:var(--ct-info);margin-top:4px">點擊以此車組單（示意）</div></div>`,
        style: {
          background: "rgba(10,16,27,0.95)",
          border: "1px solid #243149",
          borderRadius: "8px",
          padding: "8px 10px",
        },
      };
    }
    // 路線停靠點
    if (object.seq && object.action) {
      return {
        html: `<div style="font-family:'Noto Sans TC',sans-serif"><b style="color:var(--ct-text)">${object.seq}. ${escapeHtml(object.station_name)}</b><div style="font-size:11px;color:var(--ct-text-dim)">${escapeHtml(object.action)} ${escapeHtml(object.quantity)} 台</div></div>`,
        style: {
          background: "rgba(10,16,27,0.95)",
          border: "1px solid #243149",
          borderRadius: "8px",
          padding: "8px 10px",
        },
      };
    }
    return {
      html: buildTooltipHtml(object),
      style: {
        background: "rgba(10,16,27,0.95)",
        border: "1px solid #243149",
        borderRadius: "8px",
        boxShadow: "0 6px 20px rgba(0,0,0,0.55)",
        padding: "10px 12px",
      },
    };
  }, []);

  // 沒有站點時不要把地圖整個換掉——調度員需要地圖一直在那裡當空間參考，
  // 只是上面沒有標示而已。改成疊一張輕量提示（ADR-322）。
  const emptyNotice = stations.length ? null : (
    <div className="map-empty-notice">目前篩選沒有站點</div>
  );

  return (
    <Card className="map-card" styles={{ body: { padding: 0, height: "100%" } }}>
      <SharedMap
        ariaLabel="站點即時壓力地圖"
        className="map-fill"
        initialViewState={presentationConfig.maps.dashboard}
        layers={layers}
        getTooltip={getTooltip}
        overlay={<><StationLegend dimension={dimension} />{layerControl}{emptyNotice}</>}
        focusTarget={focus}
      />
    </Card>
  );
}
