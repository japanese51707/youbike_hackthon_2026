import { Card, Empty, Space, Tag, Typography } from "antd";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
} from "react-leaflet";
import presentationConfig from "../../config/presentation.json";
import { stationStatusLabels } from "../../utils/formatters.js";
import { getStationColor } from "../../utils/mapPresentation.js";

export default function StationMap({ stations, dimension, onSelectStation }) {
  if (!stations.length) {
    return (
      <Card className="map-card">
        <Empty description="目前篩選沒有站點" />
      </Card>
    );
  }

  const mapSettings = presentationConfig.maps.dashboard;

  return (
    <Card className="map-card" styles={{ body: { padding: 0 } }}>
      <MapContainer
        center={mapSettings.center}
        zoom={mapSettings.zoom}
        scrollWheelZoom
        className="station-map"
      >
        <TileLayer
          attribution={presentationConfig.tileLayer.attribution}
          url={presentationConfig.tileLayer.url}
        />
        {stations.map((station) => {
          const color = getStationColor(station, dimension);
          return (
            <CircleMarker
              key={station.station_id}
              center={[station.lat, station.lng]}
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: presentationConfig.markers.fillOpacity,
              }}
              radius={presentationConfig.markers.stationRadius}
              eventHandlers={{ click: () => onSelectStation(station.station_id) }}
            >
              <Popup>
                <Space direction="vertical" size={3}>
                  <Typography.Text strong>{station.station_name}</Typography.Text>
                  <Typography.Text>{station.district}</Typography.Text>
                  <div>
                    <Tag color={color}>{stationStatusLabels[station.status]}</Tag>
                    可借 {station.available_bikes}／可還 {station.available_docks}
                  </div>
                  <Typography.Link onClick={() => onSelectStation(station.station_id)}>
                    查看詳情
                  </Typography.Link>
                </Space>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </Card>
  );
}
