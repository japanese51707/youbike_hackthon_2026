import presentationConfig from "../config/presentation.json";

export const stationStatusColors = presentationConfig.statusColors;

export function getStationColor(station, dimension = "status") {
  if (dimension === "usage") {
    const band = presentationConfig.usageBands.find(
      (item) => station.usage_rate <= item.max,
    );
    return band?.color ?? presentationConfig.fallbackColor;
  }
  return (
    stationStatusColors[station.status] ?? presentationConfig.fallbackColor
  );
}
