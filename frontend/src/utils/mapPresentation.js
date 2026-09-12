import { getRentalStatus } from "./stationAppearance.js";
import presentationConfig from "../config/presentation.json";

export const stationStatusColors = presentationConfig.statusColors;

export function getStationColor(station, dimension = "status") {
  if (getRentalStatus(station) === "offline") return stationStatusColors.offline;
  if (dimension === "usage") {
    const band = presentationConfig.usageBands.find(
      (item) => station.usage_rate <= item.max,
    );
    return band?.color ?? presentationConfig.fallbackColor;
  }
  return (
    stationStatusColors[getRentalStatus(station)] ?? presentationConfig.fallbackColor
  );
}

export function hexToRgba(hexColor, opacity = 1) {
  const normalized = hexColor.replace("#", "");
  if (!/^[0-9a-fA-F]{6}$/.test(normalized)) {
    throw new Error(`無效的地圖顏色：${hexColor}`);
  }
  return [
    Number.parseInt(normalized.slice(0, 2), 16),
    Number.parseInt(normalized.slice(2, 4), 16),
    Number.parseInt(normalized.slice(4, 6), 16),
    Math.round(Math.min(1, Math.max(0, opacity)) * 255),
  ];
}
