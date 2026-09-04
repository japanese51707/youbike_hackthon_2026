import { Card, Checkbox, Empty } from "antd";
import { useCallback, useMemo, useState } from "react";
import SharedMap from "../map/SharedMap.jsx";
import { createStationGaugeLayer } from "../map/layers/stationGaugeLayer.js";
import { createVoronoiLayer } from "../map/layers/voronoiLayer.js";
import { createDensityLayer } from "../map/layers/densityLayer.js";
import presentationConfig from "../../config/presentation.json";
import { stationStatusLabels } from "../../utils/formatters.js";
import { getStationColor } from "../../utils/mapPresentation.js";

const layerOptions = [
  { label: "站點狀態環", value: "stations" },
  { label: "高負載熱區（Voronoi）", value: "zones" },
  { label: "容量密度基底（Hexagon）", value: "density" },
];

const statusToneColor = {
  empty: "#ff6b6b",
  low: "#ffa94d",
  normal: "#38d9a9",
  high: "#4dabf7",
  full: "#9775fa",
};

function buildTooltipHtml(station) {
  const capacity = Number(station.total_docks) || 0;
  const bikes = Number(station.available_bikes) || 0;
  const ratio = capacity > 0 ? Math.round((bikes / capacity) * 100) : 0;
  const tone = statusToneColor[station.status] ?? "#38d9a9";
  const statusLabel = stationStatusLabels[station.status] ?? station.status;
  const stale = station.data_freshness && station.data_freshness !== "live";

  return `
    <div style="font-family:'Noto Sans TC',sans-serif;min-width:210px">
      <div style="font-weight:700;font-size:13px;color:#f1f5f9">${station.station_name}</div>
      <div style="font-size:11px;color:#8ea0b5;margin-bottom:8px">${station.district}｜${station.area_type ?? ""}</div>
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px">
        <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${tone}"></span>
        <span style="font-size:12px;color:#e5ecf5">${statusLabel}</span>
        ${stale ? '<span style="font-size:10px;color:#ffa94d">資料延遲</span>' : ""}
      </div>
      <div style="height:6px;border-radius:3px;background:rgba(148,163,184,0.25);overflow:hidden">
        <div style="height:100%;width:${ratio}%;background:${tone}"></div>
      </div>
      <div style="display:flex;justify-content:space-between;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:11px;color:#cbd5e1;margin-top:6px">
        <span>可借 ${bikes}</span>
        <span>可還 ${Number(station.available_docks) || 0}</span>
        <span>${ratio}%／${capacity}</span>
      </div>
    </div>
  `;
}

export default function StationMap({ stations, dimension, onSelectStation }) {
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
    return composed.filter(Boolean);
  }, [activeLayers, dimension, onSelectStation, stations]);

  const layerControl = (
    <div className="map-layer-control">
      <div className="map-layer-control-title">圖層</div>
      <Checkbox.Group
        options={layerOptions}
        value={activeLayers}
        onChange={setActiveLayers}
      />
    </div>
  );
  const getTooltip = useCallback(({ object }) => {
    if (!object) return null;
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

  if (!stations.length) {
    return (
      <Card className="map-card">
        <Empty description="目前篩選沒有站點" />
      </Card>
    );
  }

  return (
    <Card className="map-card" styles={{ body: { padding: 0 } }}>
      <SharedMap
        ariaLabel="站點即時壓力地圖"
        className="station-map"
        initialViewState={presentationConfig.maps.dashboard}
        layers={layers}
        getTooltip={getTooltip}
        overlay={layerControl}
      />
    </Card>
  );
}
