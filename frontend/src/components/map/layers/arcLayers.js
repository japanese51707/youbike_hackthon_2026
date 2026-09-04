import { ArcLayer } from "@deck.gl/layers";
import presentationConfig from "../../../config/presentation.json";
import { hexToRgba } from "../../../utils/mapPresentation.js";

// 調度弧線：連接任務路線中「相鄰停靠點」的實際航段（取車 → 補車）。
// 來源為真實任務 route，弧粗細依搬運數量；不虛構未配對的流向。
export function createRouteArcLayer(route, id = "operator-route-arcs") {
  if (!Array.isArray(route) || route.length < 2) return null;

  const legs = [];
  for (let i = 0; i < route.length - 1; i += 1) {
    const from = route[i];
    const to = route[i + 1];
    legs.push({
      from: [Number(from.lng), Number(from.lat)],
      to: [Number(to.lng), Number(to.lat)],
      quantity: Number(to.quantity) || Number(from.quantity) || 0,
    });
  }

  const source = hexToRgba(presentationConfig.layers.arcSourceColor, 0.9);
  const target = hexToRgba(presentationConfig.layers.arcTargetColor, 0.9);

  return new ArcLayer({
    id,
    data: legs,
    pickable: false,
    greatCircle: false,
    getHeight: presentationConfig.layers.arcHeight,
    getSourcePosition: (leg) => leg.from,
    getTargetPosition: (leg) => leg.to,
    getSourceColor: source,
    getTargetColor: target,
    getWidth: (leg) => leg.quantity * presentationConfig.layers.arcWidthScale,
    widthMinPixels: presentationConfig.layers.arcWidthMinPixels,
    widthUnits: "pixels",
  });
}
