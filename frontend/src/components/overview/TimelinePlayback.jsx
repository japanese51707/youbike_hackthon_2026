import { Card, Empty, Slider, Tag, Typography } from "antd";
import { useCallback, useMemo, useState } from "react";
import StationLegend from "../map/StationLegend.jsx";
import SharedMap from "../map/SharedMap.jsx";
import { createStationLayer } from "../map/layers/stationLayers.js";
import presentationConfig from "../../config/presentation.json";
import { stationStatusLabels } from "../../utils/formatters.js";
import { getStationColor } from "../../utils/mapPresentation.js";

export default function TimelinePlayback({ timeline, stations }) {
  const [frameIndex, setFrameIndex] = useState(0);
  const frame = timeline.frames[frameIndex];
  const frameStations = useMemo(
    () =>
      (frame?.stations ?? [])
        .map((station) => {
          const source = stations.find(
            (item) => item.station_id === station.station_id,
          );
          return source ? { ...source, ...station } : null;
        })
        .filter(Boolean),
    [frame, stations],
  );
  const layers = useMemo(
    () => [
      createStationLayer({
        id: `timeline-stations-${frameIndex}`,
        data: frameStations,
        getColor: getStationColor,
        radiusPixels: presentationConfig.markers.timelineRadiusPixels,
      }),
    ],
    [frameIndex, frameStations],
  );
  const getTooltip = useCallback(({ object }) => {
    if (!object) return null;
    return {
      text: `${object.station_name}\n${stationStatusLabels[object.status] ?? object.status}｜可借 ${object.available_bikes} 台｜緊急度 ${object.urgency_score}`,
    };
  }, []);

  if (!timeline.frames.length) {
    return <Card><Empty description="目前沒有時間軸資料" /></Card>;
  }

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
      <SharedMap
        ariaLabel="站點壓力歷史時間軸地圖"
        className="timeline-map"
        initialViewState={presentationConfig.maps.timeline}
        layers={layers}
        getTooltip={getTooltip}
        overlay={<StationLegend />}
      />
    </Card>
  );
}
