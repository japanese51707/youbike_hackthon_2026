import { ScatterplotLayer } from "@deck.gl/layers";
import presentationConfig from "../../../config/presentation.json";
import { hexToRgba } from "../../../utils/mapPresentation.js";

export function createStationLayer({
  data,
  getColor,
  id,
  onSelectStation,
  radiusPixels = presentationConfig.markers.stationRadiusPixels,
}) {
  return new ScatterplotLayer({
    id,
    data,
    pickable: true,
    autoHighlight: true,
    highlightColor: [255, 255, 255, 110],
    radiusUnits: "pixels",
    getPosition: (station) => [Number(station.lng), Number(station.lat)],
    getRadius: radiusPixels,
    getFillColor: (station) =>
      hexToRgba(getColor(station), presentationConfig.markers.fillOpacity),
    getLineColor: [255, 255, 255, 230],
    getLineWidth: 1,
    lineWidthUnits: "pixels",
    stroked: true,
    onClick: ({ object }) => {
      if (object?.station_id && onSelectStation) {
        onSelectStation(object.station_id);
      }
    },
  });
}
