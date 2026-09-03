import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import presentationConfig from "../../../config/presentation.json";
import { hexToRgba } from "../../../utils/mapPresentation.js";

export function createRouteLayers(route) {
  const path = route.map((stop) => [Number(stop.lng), Number(stop.lat)]);

  return [
    new PathLayer({
      id: "operator-route-path",
      data: [{ path }],
      getPath: (item) => item.path,
      getColor: hexToRgba(presentationConfig.route.lineColor),
      getWidth: presentationConfig.route.lineWidthPixels,
      widthUnits: "pixels",
      pickable: false,
    }),
    new ScatterplotLayer({
      id: "operator-route-stops",
      data: route,
      pickable: true,
      radiusUnits: "pixels",
      getPosition: (stop) => [Number(stop.lng), Number(stop.lat)],
      getRadius: presentationConfig.markers.routeRadiusPixels,
      getFillColor: (stop) =>
        hexToRgba(
          stop.stop_status === "completed"
            ? presentationConfig.route.completedColor
            : presentationConfig.route.pendingColor,
          presentationConfig.markers.fillOpacity,
        ),
      getLineColor: [255, 255, 255, 230],
      getLineWidth: 1,
      lineWidthUnits: "pixels",
      stroked: true,
    }),
  ];
}
