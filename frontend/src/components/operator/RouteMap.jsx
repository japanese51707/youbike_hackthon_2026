import { Card, Empty } from "antd";
import { useCallback, useMemo } from "react";
import SharedMap from "../map/SharedMap.jsx";
import { createRouteLayers } from "../map/layers/routeLayers.js";
import { createRouteArcLayer } from "../map/layers/arcLayers.js";
import presentationConfig from "../../config/presentation.json";

export default function RouteMap({ route }) {
  const layers = useMemo(() => {
    const safeRoute = route ?? [];
    const arc = createRouteArcLayer(safeRoute);
    return [...(arc ? [arc] : []), ...createRouteLayers(safeRoute)];
  }, [route]);
  const getTooltip = useCallback(({ object }) => {
    if (!object?.station_name) return null;
    return {
      text: `${object.seq}. ${object.station_name}\n${object.action} ${object.quantity} 台`,
    };
  }, []);

  if (!route?.length) {
    return <Card><Empty description="此任務沒有路線" /></Card>;
  }

  return (
    <Card title="任務路線" styles={{ body: { padding: 0 } }}>
      <SharedMap
        ariaLabel="調度任務路線地圖"
        className="route-map"
        initialViewState={{
          longitude: Number(route[0].lng),
          latitude: Number(route[0].lat),
          zoom: presentationConfig.maps.route.zoom,
        }}
        layers={layers}
        getTooltip={getTooltip}
      />
    </Card>
  );
}
