import { HexagonLayer } from "@deck.gl/aggregation-layers";
import presentationConfig from "../../../config/presentation.json";

// 柱高＝格內車柱總數（容量密度）；顏色＝格內平均使用率（0% 空、50% 平衡、100% 滿）。
// 不是歷史借還流量。缺使用率時當 50%，避免被當成空站。
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
    opacity: 0.55,
    colorAggregation: "MEAN",
    elevationAggregation: "SUM",
    colorDomain: presentationConfig.layers.hexagonColorDomain,
    colorRange: presentationConfig.layers.hexagonColorRange,
    getPosition: (station) => [Number(station.lng), Number(station.lat)],
    getElevationWeight: (station) => Number(station.total_docks) || 0,
    getColorWeight: (station) => {
      const usage = Number(station.usage_rate);
      return Number.isFinite(usage) ? usage : 50;
    },
  });
}
