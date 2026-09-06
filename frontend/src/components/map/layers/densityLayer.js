import { HexagonLayer } from "@deck.gl/aggregation-layers";
import presentationConfig from "../../../config/presentation.json";

// 站點容量密度基底（HexagonLayer）：以 total_docks 作為聚合權重，
// 作為暗色底圖上的對比基底。權重來自既有站點欄位，非歷史借還量，命名據實標示。
export function createDensityLayer({ data, id }) {
  if (!Array.isArray(data) || !data.length) return null;

  return new HexagonLayer({
    id,
    data,
    pickable: false,
    extruded: true,
    radius: presentationConfig.layers.hexagonRadiusMeters,
    elevationScale: presentationConfig.layers.hexagonElevationScale,
    coverage: 0.85,
    opacity: 0.35,
    colorRange: presentationConfig.layers.hexagonColorRange,
    getPosition: (station) => [Number(station.lng), Number(station.lat)],
    getElevationWeight: (station) => Number(station.total_docks) || 0,
    getColorWeight: (station) => Number(station.total_docks) || 0,
  });
}
