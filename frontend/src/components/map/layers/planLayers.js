import presentationConfig from "../../../config/presentation.json";
import { hexToRgba } from "../../../utils/mapPresentation.js";
import { dashSegments, joinPaths, splitPathByWaypoints } from "../../../utils/routePath.js";
import { PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
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
    getFillColor: hexToRgba(presentationConfig.route.lineColor, 0.08),
    getLineColor: hexToRgba(presentationConfig.route.lineColor, 0.65),
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
    getLineColor: [255, 254, 250, 240],
    getLineWidth: 2,
    lineWidthUnits: "pixels",
    pickable: false,
  });
}

function isDoneStop(stop) {
  return stop?.station_status === "completed" || stop?.station_status === "done";
}

// 多點路線規劃（類 Google Maps）：起點 → 各停靠點依序連線的折線 + 編號標記
// （取車橘／補車綠、圓點內顯示停靠順序 1,2,3…）+ 起點標記。route 已是「先載後放」順序。
// geometry：後端 /routing/road 回的實走道路折線 [[lng,lat],...]。
// 有給就用它畫線（沿著路），沒給就退回「起點→各站」的直線串接。
// currentIndex：目前這站；這站之後的路段改畫虛線，提醒後面還要去哪。
export function createPlanRouteLayers({
  start,
  route,
  geometry,
  id = "plan-route",
  currentIndex = null,
}) {
  if (!start || !Array.isArray(route) || !route.length) return [];
  const roadPath =
    Array.isArray(geometry) && geometry.length >= 2
      ? geometry.filter(
          (p) => Array.isArray(p) && Number.isFinite(p[0]) && Number.isFinite(p[1]),
        )
      : null;
  const waypoints = [start, ...route];
  const path =
    roadPath && roadPath.length >= 2
      ? roadPath
      : waypoints.map((point) => [point.lng, point.lat]);
  const splitAt =
    Number.isInteger(currentIndex) && currentIndex >= 0 && currentIndex < route.length
      ? currentIndex
      : null;
  let solidPath = path;
  let futurePath = [];
  if (splitAt !== null) {
    const legs = splitPathByWaypoints(path, waypoints);
    solidPath = joinPaths(legs.slice(0, splitAt + 1));
    futurePath = joinPaths(legs.slice(splitAt + 1));
  }
  // 帶序號的停靠點（1-based）
  const numbered = route.map((stop, i) => ({ ...stop, seq: i + 1, stopIndex: i }));
  const lineWidth = roadPath ? 5 : 4;

  return [
    // 目前這段：實線
    solidPath.length >= 2
      ? new PathLayer({
          id: `${id}-path`,
          data: [{ path: solidPath }],
          getPath: (item) => item.path,
          getColor: hexToRgba(presentationConfig.route.lineColor, 0.9),
          getWidth: lineWidth,
          widthUnits: "pixels",
          capRounded: true,
          jointRounded: true,
          pickable: false,
        })
      : null,
    // 後面還沒走到的路段：虛線指引
    futurePath.length >= 2
      ? new PathLayer({
          id: `${id}-path-ahead`,
          data: dashSegments(futurePath).map((segment) => ({ path: segment })),
          getPath: (item) => item.path,
          getColor: hexToRgba(presentationConfig.route.lineColor, 0.48),
          getWidth: Math.max(3, lineWidth - 1),
          widthUnits: "pixels",
          capRounded: true,
          jointRounded: true,
          pickable: false,
        })
      : null,
    // 起點標記（車輛出發位置）：外圈深色小點
    new ScatterplotLayer({
      id: `${id}-start`,
      data: [start],
      getPosition: (d) => [d.lng, d.lat],
      getRadius: 7,
      radiusUnits: "pixels",
      stroked: true,
      getFillColor: fleetPlannerConfig.vehicleColor ?? [70, 90, 120, 255],
      getLineColor: [255, 255, 255, 230],
      getLineWidth: 2,
      lineWidthUnits: "pixels",
      pickable: false,
    }),
    // 停靠點圓點（取車橘／補車綠），放大以容納序號
    new ScatterplotLayer({
      id: `${id}-stops`,
      data: numbered,
      pickable: true,
      getPosition: (stop) => [stop.lng, stop.lat],
      getRadius: (stop) => (splitAt !== null && stop.stopIndex === splitAt ? 15 : 12),
      radiusUnits: "pixels",
      stroked: true,
      getFillColor: (stop) => {
        const base =
          stop.action === "補車"
            ? fleetPlannerConfig.stopDropoffColor
            : fleetPlannerConfig.stopPickupColor;
        if (splitAt !== null && stop.stopIndex > splitAt) {
          return [base[0], base[1], base[2], 140];
        }
        if (isDoneStop(stop)) {
          return [base[0], base[1], base[2], 120];
        }
        return base;
      },
      getLineColor: [255, 255, 255, 230],
      getLineWidth: 2,
      lineWidthUnits: "pixels",
    }),
    // 停靠順序編號（疊在圓點上，像 Google Maps 的 1,2,3）
    new TextLayer({
      id: `${id}-seq`,
      data: numbered,
      getPosition: (stop) => [stop.lng, stop.lat],
      getText: (stop) => String(stop.seq),
      getSize: 13,
      sizeUnits: "pixels",
      getColor: (stop) =>
        splitAt !== null && stop.stopIndex > splitAt
          ? [255, 255, 255, 190]
          : [255, 255, 255, 255],
      fontWeight: 700,
      getTextAnchor: "middle",
      getAlignmentBaseline: "center",
      pickable: false,
    }),
  ].filter(Boolean);
}
