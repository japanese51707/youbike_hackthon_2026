import { PolygonLayer } from "@deck.gl/layers";
import { Delaunay } from "d3-delaunay";
import presentationConfig from "../../../config/presentation.json";
import { hexToRgba } from "../../../utils/mapPresentation.js";

// 依站點位置生成 Voronoi 泰森多邊形（每站的「勢力範圍」）。
// 顏色沿用站點 status/usage 色，低透明度呈現高負載熱區；資料全部來自既有站點，不捏造。
export function createVoronoiLayer({ data, getColor, id }) {
  if (!Array.isArray(data) || data.length < 3) return null;

  const points = data.map((station) => [Number(station.lng), Number(station.lat)]);
  const lngs = points.map((p) => p[0]);
  const lats = points.map((p) => p[1]);
  const pad = presentationConfig.layers.voronoiPaddingDeg;
  const bounds = [
    Math.min(...lngs) - pad,
    Math.min(...lats) - pad,
    Math.max(...lngs) + pad,
    Math.max(...lats) + pad,
  ];

  const delaunay = Delaunay.from(points);
  const voronoi = delaunay.voronoi(bounds);

  const cells = data
    .map((station, index) => {
      const polygon = voronoi.cellPolygon(index);
      return polygon ? { station, polygon } : null;
    })
    .filter(Boolean);

  const lineColor = hexToRgba(presentationConfig.layers.voronoiLineColor, 1);

  return new PolygonLayer({
    id,
    data: cells,
    pickable: false,
    stroked: true,
    filled: true,
    getPolygon: (cell) => cell.polygon,
    getFillColor: (cell) =>
      hexToRgba(getColor(cell.station), presentationConfig.layers.voronoiOpacity),
    getLineColor: lineColor,
    getLineWidth: 1,
    lineWidthUnits: "pixels",
  });
}
