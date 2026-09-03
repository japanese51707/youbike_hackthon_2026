import { Card, Slider, Space, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import presentationConfig from "../../config/presentation.json";
import { stationStatusLabels } from "../../utils/formatters.js";
import { stationStatusColors } from "../../utils/mapPresentation.js";

export default function TimelinePlayback({ timeline, stations }) {
  const [frameIndex, setFrameIndex] = useState(0);
  const frame = timeline.frames[frameIndex];
  const stationNames = useMemo(
    () => Object.fromEntries(stations.map((item) => [item.station_id, item.station_name])),
    [stations],
  );
  const mapSettings = presentationConfig.maps.timeline;

  return (
    <Card title={`${timeline.district} 站點壓力時間軸`} extra={<Tag>{timeline.date}</Tag>}>
      <div className="timeline-toolbar">
        <Typography.Text strong>{frame.time}</Typography.Text>
        <Slider
          min={0}
          max={timeline.frames.length - 1}
          step={1}
          value={frameIndex}
          marks={Object.fromEntries(timeline.frames.map((item, index) => [index, item.time]))}
          tooltip={{ formatter: (value) => timeline.frames[value]?.time }}
          onChange={setFrameIndex}
        />
      </div>
      <MapContainer center={mapSettings.center} zoom={mapSettings.zoom} className="timeline-map">
        <TileLayer
          attribution={presentationConfig.tileLayer.attribution}
          url={presentationConfig.tileLayer.url}
        />
        {frame.stations.map((station) => {
          const source = stations.find((item) => item.station_id === station.station_id);
          if (!source) return null;
          const color = stationStatusColors[station.status] || presentationConfig.fallbackColor;
          return (
            <CircleMarker
              key={station.station_id}
              center={[source.lat, source.lng]}
              radius={presentationConfig.markers.timelineRadius}
              pathOptions={{
                color,
                fillColor: color,
                fillOpacity: presentationConfig.markers.fillOpacity,
              }}
            >
              <Popup>
                <Space direction="vertical" size={2}>
                  <Typography.Text strong>{stationNames[station.station_id]}</Typography.Text>
                  <Tag color={color}>{stationStatusLabels[station.status] || station.status}</Tag>
                  <Typography.Text>可借 {station.available_bikes} 台</Typography.Text>
                  <Typography.Text>緊急度 {station.urgency_score}</Typography.Text>
                </Space>
              </Popup>
            </CircleMarker>
          );
        })}
      </MapContainer>
    </Card>
  );
}
