import { Card, Empty, Tag, Typography } from "antd";
import {
  CircleMarker,
  MapContainer,
  Polyline,
  Popup,
  TileLayer,
} from "react-leaflet";
import presentationConfig from "../../config/presentation.json";

export default function RouteMap({ route }) {
  if (!route?.length) {
    return <Card><Empty description="此任務沒有路線" /></Card>;
  }

  const positions = route.map((stop) => [stop.lat, stop.lng]);

  return (
    <Card title="任務路線" styles={{ body: { padding: 0 } }}>
      <MapContainer
        center={positions[0]}
        zoom={presentationConfig.maps.route.zoom}
        className="route-map"
      >
        <TileLayer
          attribution={presentationConfig.tileLayer.attribution}
          url={presentationConfig.tileLayer.url}
        />
        <Polyline
          positions={positions}
          pathOptions={{
            color: presentationConfig.route.lineColor,
            weight: presentationConfig.route.lineWeight,
          }}
        />
        {route.map((stop) => (
          <CircleMarker
            key={stop.seq}
            center={[stop.lat, stop.lng]}
            radius={presentationConfig.markers.routeRadius}
            pathOptions={{
              color:
                stop.stop_status === "completed"
                  ? presentationConfig.route.completedColor
                  : presentationConfig.route.pendingColor,
              fillOpacity: presentationConfig.markers.fillOpacity,
            }}
          >
            <Popup>
              <Typography.Text strong>{stop.seq}. {stop.station_name}</Typography.Text>
              <br />
              <Tag>{stop.action} {stop.quantity} 台</Tag>
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </Card>
  );
}
