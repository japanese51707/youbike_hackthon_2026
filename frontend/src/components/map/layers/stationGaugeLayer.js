import { IconLayer } from "@deck.gl/layers";
import presentationConfig from "../../../config/presentation.json";
import { getGaugeIcon } from "../../../utils/gaugeIcon.js";

// 環形進度環站點圖層：弧長＝可借比例（available_bikes / total_docks），
// 顏色＝getColor 提供的風險/狀態色。像素單位維持各 zoom 一致。
export function createStationGaugeLayer({
  data,
  getColor,
  id,
  onSelectStation,
  dimension = "status",
  sizePixels = 40,
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
    getIcon: (station) => getGaugeIcon(availableRatio(station), getColor(station)),
    getSize: sizePixels,
    sizeUnits: "pixels",
    updateTriggers: {
      getIcon: [dimension],
    },
    onClick: ({ object }) => {
      if (object?.station_id && onSelectStation) {
        onSelectStation(object.station_id);
      }
    },
  });
}
