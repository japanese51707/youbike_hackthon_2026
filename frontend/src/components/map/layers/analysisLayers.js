import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { ArcLayer, LineLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { Delaunay } from "d3-delaunay";
import presentationConfig from "../../../config/presentation.json";
import {
  buildKnnNetwork,
  degreeCentrality,
  getisOrdGiStar,
  giStarFillColor,
  interpolateColorRange,
  stationPressure,
  stationsWithCoords,
} from "../../../utils/spatialStats.js";
import { pairDispatchFlows } from "../../../utils/twinFlow.js";

const HEAT_RANGE = [
  [13, 30, 54],
  [23, 58, 92],
  [45, 171, 247],
  [56, 217, 169],
  [255, 169, 77],
  [255, 107, 107],
];

// 只保留座標為有限數的站點，避免缺經緯度（NaN）污染 Voronoi/格點幾何，
// 畫出「看起來像分析、其實是壞掉的幾何」——與專案「不捏造」原則相衝。
function withFiniteCoords(data) {
  return stationsWithCoords(data);
}

function bounds(data, pad = presentationConfig.layers.voronoiPaddingDeg) {
  const lngs = data.map((s) => Number(s.lng));
  const lats = data.map((s) => Number(s.lat));
  return [
    Math.min(...lngs) - pad,
    Math.min(...lats) - pad,
    Math.max(...lngs) + pad,
    Math.max(...lats) + pad,
  ];
}

// KDE 壓力熱力圖：以站點壓力為權重的核密度
export function createKdeHeatmapLayer({ data, id = "kde" }) {
  const pts = withFiniteCoords(data);
  if (!pts.length) return null;
  return new HeatmapLayer({
    id,
    data: pts,
    getPosition: (s) => [Number(s.lng), Number(s.lat)],
    getWeight: (s) => stationPressure(s) * 100,
    radiusPixels: 70,
    intensity: 1,
    threshold: 0.05,
    colorRange: HEAT_RANGE,
    opacity: 0.6,
  });
}

// 鄰近網路 + 中心性：邊 + 節點；圓圈大小與顏色都依中心性連續漸層。
export function createNetworkLayers({ data, onSelectStation, id = "network" }) {
  const pts = withFiniteCoords(data);
  if (pts.length < 2) return [];
  const edges = buildKnnNetwork(pts, { k: 3 });
  const centrality = degreeCentrality(pts, edges);
  const ramp = presentationConfig.layers.centralityColorRange;
  const scoreOf = (station) => centrality.get(station?.station_id) || 0;

  return [
    new LineLayer({
      id: `${id}-edges`,
      data: edges,
      getSourcePosition: (e) => [Number(e.from.lng), Number(e.from.lat)],
      getTargetPosition: (e) => [Number(e.to.lng), Number(e.to.lat)],
      getColor: (edge) => interpolateColorRange(ramp, Math.max(scoreOf(edge.from), scoreOf(edge.to)), 150),
      getWidth: 2,
      widthUnits: "pixels",
      pickable: false,
    }),
    new ScatterplotLayer({
      id: `${id}-nodes`,
      data: pts,
      pickable: true,
      getPosition: (s) => [Number(s.lng), Number(s.lat)],
      radiusUnits: "pixels",
      getRadius: (s) => 6 + scoreOf(s) * 20,
      getFillColor: (s) => interpolateColorRange(ramp, scoreOf(s), 220),
      getLineColor: [255, 255, 255, 200],
      getLineWidth: 1,
      lineWidthUnits: "pixels",
      stroked: true,
      onClick: ({ object }) => {
        if (object?.station_id && onSelectStation) onSelectStation(object.station_id);
      },
    }),
  ];
}

// 調度/流向弧線（示意 OD）：取車站 → 補車站，粗細依需求數量。
// 無真實 trip OD，以調度建議示意；接上真實 OD 才是實際流向。
export function createFlowArcLayer({ recommendations, pairs, id = "flow" }) {
  const data = pairs ?? pairDispatchFlows(recommendations);
  if (!data.length) return null;

  return new ArcLayer({
    id,
    data,
    getSourcePosition: (pair) => [Number(pair.from.lng), Number(pair.from.lat)],
    getTargetPosition: (pair) => [Number(pair.to.lng), Number(pair.to.lat)],
    getSourceColor: [...presentationConfig.layers.arcSourceRgb, 200],
    getTargetColor: [...presentationConfig.layers.arcTargetRgb, 200],
    getWidth: (pair) => Math.max(1.4, (pair.quantity || 0) * 0.28),
    widthUnits: "pixels",
    getHeight: (pair) => Math.min(0.9, 0.18 + (Number(pair.km) || 0) * 0.08),
    pickable: false,
  });
}

// Voronoi 勢力範圍 + Getis-Ord Gi* 熱點顯著性著色
export function createGiStarVoronoiLayer({ data, id = "gi-voronoi" }) {
  const pts = withFiniteCoords(data);
  if (pts.length < 3) return null;
  const gi = getisOrdGiStar(pts, { radiusKm: 3 });
  const points = pts.map((s) => [Number(s.lng), Number(s.lat)]);
  const delaunay = Delaunay.from(points);
  const voronoi = delaunay.voronoi(bounds(pts));

  const cells = pts
    .map((station, index) => {
      const polygon = voronoi.cellPolygon(index);
      if (!polygon) return null;
      return { station, polygon, z: gi[index].z };
    })
    .filter(Boolean);

  return new PolygonLayer({
    id,
    data: cells,
    stroked: true,
    filled: true,
    getPolygon: (c) => c.polygon,
    getFillColor: (c) => giStarFillColor(c.z),
    getLineColor: [220, 228, 238, 80],
    getLineWidth: 1,
    lineWidthUnits: "pixels",
    pickable: false,
  });
}
