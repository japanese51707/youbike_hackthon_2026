import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import { ArcLayer, LineLayer, PolygonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { Delaunay } from "d3-delaunay";
import presentationConfig from "../../../config/presentation.json";
import { haversineKm } from "../../../utils/geo.js";
import {
  buildKnnNetwork,
  degreeCentrality,
  getisOrdGiStar,
  giStarClass,
  stationPressure,
} from "../../../utils/spatialStats.js";

const HEAT_RANGE = [
  [13, 30, 54],
  [23, 58, 92],
  [45, 171, 247],
  [56, 217, 169],
  [255, 169, 77],
  [255, 107, 107],
];

const GAP_RANGE = [
  [12, 24, 40],
  [23, 58, 92],
  [120, 90, 40],
  [255, 169, 77],
  [255, 107, 107],
];

// 只保留座標為有限數的站點，避免缺經緯度（NaN）污染 Voronoi/格點幾何，
// 畫出「看起來像分析、其實是壞掉的幾何」——與專案「不捏造」原則相衝。
function hasFiniteCoords(s) {
  return Number.isFinite(Number(s?.lng)) && Number.isFinite(Number(s?.lat));
}

function withFiniteCoords(data) {
  return (data ?? []).filter(hasFiniteCoords);
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

// 覆蓋缺口：鋪格點，權重＝到最近站點距離（越遠越紅），凸顯服務死角
export function createCoverageGapLayer({ data, id = "coverage", steps = 26 }) {
  const pts = withFiniteCoords(data);
  if (!pts.length) return null;
  const [minLng, minLat, maxLng, maxLat] = bounds(pts, 0.04);
  const grid = [];
  for (let i = 0; i <= steps; i += 1) {
    for (let j = 0; j <= steps; j += 1) {
      const lng = minLng + ((maxLng - minLng) * i) / steps;
      const lat = minLat + ((maxLat - minLat) * j) / steps;
      let nearest = Infinity;
      for (const s of pts) {
        const d = haversineKm({ lat, lng }, { lat: Number(s.lat), lng: Number(s.lng) });
        if (d < nearest) nearest = d;
      }
      grid.push({ lng, lat, gap: Math.min(nearest, 4) });
    }
  }
  return new HeatmapLayer({
    id,
    data: grid,
    getPosition: (p) => [p.lng, p.lat],
    getWeight: (p) => p.gap,
    radiusPixels: 60,
    intensity: 1,
    threshold: 0.03,
    colorRange: GAP_RANGE,
    opacity: 0.5,
  });
}

// 鄰近網路 + 中心性：邊(LineLayer) + 節點大小依中心性
export function createNetworkLayers({ data, onSelectStation, id = "network" }) {
  const pts = withFiniteCoords(data);
  if (pts.length < 2) return [];
  const edges = buildKnnNetwork(pts, { k: 3 });
  const centrality = degreeCentrality(pts, edges);

  return [
    new LineLayer({
      id: `${id}-edges`,
      data: edges,
      getSourcePosition: (e) => [Number(e.from.lng), Number(e.from.lat)],
      getTargetPosition: (e) => [Number(e.to.lng), Number(e.to.lat)],
      getColor: [102, 217, 232, 150],
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
      getRadius: (s) => 6 + (centrality.get(s.station_id) || 0) * 20,
      getFillColor: (s) => {
        const c = centrality.get(s.station_id) || 0;
        return [56, 217, 169, Math.round(120 + c * 135)];
      },
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

// 服務集水區：每站服務半徑圓（公尺）
export function createCatchmentLayer({ data, radiusKm = 0.6, id = "catchment" }) {
  const pts = withFiniteCoords(data);
  if (!pts.length) return null;
  return new ScatterplotLayer({
    id,
    data: pts,
    getPosition: (s) => [Number(s.lng), Number(s.lat)],
    getRadius: radiusKm * 1000,
    radiusUnits: "meters",
    stroked: true,
    filled: true,
    getFillColor: [56, 217, 169, 22],
    getLineColor: [56, 217, 169, 130],
    getLineWidth: 1.5,
    lineWidthUnits: "pixels",
    pickable: false,
  });
}

// 調度/流向弧線（示意 OD）：取車站 → 補車站，粗細依需求數量。
// 無真實 trip OD，以調度建議示意；接上真實 OD 才是實際流向。
export function createFlowArcLayer({ recommendations, id = "flow" }) {
  if (!recommendations?.length) return null;
  const pickups = recommendations.filter(
    (r) => r.action === "取車" && hasFiniteCoords(r),
  );
  const dropoffs = recommendations.filter(
    (r) => r.action === "補車" && hasFiniteCoords(r),
  );
  if (!dropoffs.length) return null;

  const sources = pickups.length ? pickups : dropoffs.slice(0, 1);
  const arcs = [];
  for (const s of sources) {
    for (const d of dropoffs) {
      if (s.station_id === d.station_id) continue;
      arcs.push({
        from: [Number(s.lng), Number(s.lat)],
        to: [Number(d.lng), Number(d.lat)],
        q: Number(d.quantity) || 0,
      });
    }
  }
  if (!arcs.length) return null;

  return new ArcLayer({
    id,
    data: arcs,
    getSourcePosition: (a) => a.from,
    getTargetPosition: (a) => a.to,
    getSourceColor: [255, 169, 77, 190],
    getTargetColor: [56, 217, 169, 190],
    getWidth: (a) => Math.max(2, a.q * 0.4),
    widthUnits: "pixels",
    getHeight: 0.4,
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
      return { station, polygon, cls: giStarClass(gi[index].z), z: gi[index].z };
    })
    .filter(Boolean);

  return new PolygonLayer({
    id,
    data: cells,
    stroked: true,
    filled: true,
    getPolygon: (c) => c.polygon,
    getFillColor: (c) => [...c.cls.color, 70],
    getLineColor: [36, 49, 73, 200],
    getLineWidth: 1,
    lineWidthUnits: "pixels",
    pickable: false,
  });
}
