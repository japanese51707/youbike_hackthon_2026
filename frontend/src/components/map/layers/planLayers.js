import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { fleetPlannerConfig } from "../../../config/fleetMock.js";

// 服務半徑圈（公尺為單位，隨 zoom 變化，代表載具實際可及範圍）。
export function createServiceRangeLayer({ start, radiusKm, id = "plan-range" }) {
  if (!start) return null;
  return new ScatterplotLayer({
    id,
    data: [start],
    getPosition: (d) => [d.lng, d.lat],
    getRadius: radiusKm * 1000,
    radiusUnits: "meters",
    stroked: true,
    filled: true,
    getFillColor: [102, 217, 232, 22],
    getLineColor: [102, 217, 232, 160],
    getLineWidth: 2,
    lineWidthUnits: "pixels",
    pickable: false,
  });
}

// 載具目前位置標記。
export function createVehicleLayer({ start, id = "plan-vehicle" }) {
  if (!start) return null;
  return new ScatterplotLayer({
    id,
    data: [start],
    getPosition: (d) => [d.lng, d.lat],
    getRadius: 11,
    radiusUnits: "pixels",
    stroked: true,
    getFillColor: fleetPlannerConfig.vehicleColor,
    getLineColor: [5, 7, 13, 220],
    getLineWidth: 2,
    lineWidthUnits: "pixels",
    pickable: false,
  });
}

// 示意路線：載具 → 各停靠點的折線，加停靠點標記（取車橘／補車綠）。
export function createPlanRouteLayers({ start, route, id = "plan-route" }) {
  if (!start || !Array.isArray(route) || !route.length) return [];
  const path = [
    [start.lng, start.lat],
    ...route.map((stop) => [stop.lng, stop.lat]),
  ];

  return [
    new PathLayer({
      id: `${id}-path`,
      data: [{ path }],
      getPath: (item) => item.path,
      getColor: [102, 217, 232, 200],
      getWidth: 3,
      widthUnits: "pixels",
      pickable: false,
    }),
    new ScatterplotLayer({
      id: `${id}-stops`,
      data: route,
      pickable: true,
      getPosition: (stop) => [stop.lng, stop.lat],
      getRadius: 9,
      radiusUnits: "pixels",
      stroked: true,
      getFillColor: (stop) =>
        stop.action === "補車"
          ? fleetPlannerConfig.stopDropoffColor
          : fleetPlannerConfig.stopPickupColor,
      getLineColor: [255, 255, 255, 220],
      getLineWidth: 1,
      lineWidthUnits: "pixels",
    }),
  ];
}
