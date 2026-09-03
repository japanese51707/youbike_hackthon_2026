import { Card, Empty } from "antd";
import { useCallback, useMemo } from "react";
import SharedMap from "../map/SharedMap.jsx";
import { createStationLayer } from "../map/layers/stationLayers.js";
import presentationConfig from "../../config/presentation.json";
import { stationStatusLabels } from "../../utils/formatters.js";
import { getStationColor } from "../../utils/mapPresentation.js";

export default function StationMap({ stations, dimension, onSelectStation }) {
  const layers = useMemo(
    () => [
      createStationLayer({
        id: "dashboard-stations",
        data: stations,
        getColor: (station) => getStationColor(station, dimension),
        onSelectStation,
      }),
    ],
    [dimension, onSelectStation, stations],
  );
  const getTooltip = useCallback(({ object }) => {
    if (!object) return null;
    return {
      text: `${object.station_name}\n${object.district}\n${stationStatusLabels[object.status] ?? object.status}｜可借 ${object.available_bikes}／可還 ${object.available_docks}`,
    };
  }, []);

  if (!stations.length) {
    return (
      <Card className="map-card">
        <Empty description="目前篩選沒有站點" />
      </Card>
    );
  }

  return (
    <Card className="map-card" styles={{ body: { padding: 0 } }}>
      <SharedMap
        ariaLabel="站點即時壓力地圖"
        className="station-map"
        initialViewState={presentationConfig.maps.dashboard}
        layers={layers}
        getTooltip={getTooltip}
      />
    </Card>
  );
}
