import { useMemo, useState } from "react";
import { loadTemporalPresentation } from "../api/temporalMockAdapter.js";

export default function useTemporalPresentation() {
  const result = useMemo(() => {
    try {
      return { data: loadTemporalPresentation(), error: null };
    } catch (error) {
      return { data: null, error };
    }
  }, []);
  const [mode, setMode] = useState("live");
  const [stationId, setStationId] = useState(null);

  const stations = result.data?.stations ?? [];
  const effectiveStationId = stationId ?? stations[0]?.stationId ?? null;
  const station =
    stations.find((item) => item.stationId === effectiveStationId) ?? null;

  return {
    error: result.error,
    mode,
    setMode,
    station,
    stationId: effectiveStationId,
    setStationId,
    stations,
    timezone: result.data?.timezone ?? null,
  };
}
