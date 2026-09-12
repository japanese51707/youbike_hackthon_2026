import presentationConfig from "../../../config/presentation.json";
import { createStationGaugeLayer } from "./stationGaugeLayer.js";

// 歷史時間軸也使用相同品牌標記，維持既有呼叫介面。
export function createStationLayer({ radiusPixels = presentationConfig.markers.stationRadiusPixels, ...props }) {
  return createStationGaugeLayer({ ...props, sizePixels: Math.max(28, radiusPixels * 2.5) });
}
