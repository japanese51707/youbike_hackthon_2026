import { IconLayer } from "@deck.gl/layers";
import { hasAvailableElectricBike } from "../../../utils/stationAppearance.js";
import { getStationPinIcon } from "../../../utils/stationPinIcon.js";

// 官方風格站點圖釘：弧線數＝可借比例，顏色＝租借狀態；分析維度另有圖例。
export function createStationGaugeLayer({
  data,
  getColor,
  id,
  onSelectStation,
  dimension = "status",
  sizePixels = 36,
}) {
  const availableRatio = (station) => {
    const capacity = Number(station.total_docks);
    if (!Number.isFinite(capacity) || capacity <= 0) return 0;
    return Number(station.available_bikes) / capacity;
  };

  return new IconLayer({
    id,
    data,
    pickable: true,
    getPosition: (station) => [Number(station.lng), Number(station.lat)],
    getIcon: (station) => getStationPinIcon(availableRatio(station), getColor(station), hasAvailableElectricBike(station)),
    getSize: typeof sizePixels === "function" ? sizePixels : () => sizePixels,
    sizeUnits: "pixels",
    updateTriggers: {
      getIcon: [dimension, getColor],
      getSize: [sizePixels],
    },
    onClick: ({ object }) => {
      if (object?.station_id && onSelectStation) {
        onSelectStation(object.station_id);
      }
    },
  });
}
