import temporalFixture from "../mock/temporal_mock_data.json";

const FIXED_OFFSETS = [30, 60];
const OFFSET_TIMESTAMP_PATTERN = /(Z|[+-]\d{2}:\d{2})$/;

function requireObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`Temporal Mock 格式錯誤：${label} 必須是物件`);
  }
  return value;
}

function requireArray(value, label) {
  if (!Array.isArray(value)) {
    throw new Error(`Temporal Mock 格式錯誤：${label} 必須是陣列`);
  }
  return value;
}

function requireOffsetTimestamp(value, label) {
  if (typeof value !== "string" || !OFFSET_TIMESTAMP_PATTERN.test(value)) {
    throw new Error(`Temporal Mock 格式錯誤：${label} 必須包含 offset`);
  }
  return value;
}

function requireFiniteNumber(value, label) {
  if (!Number.isFinite(value)) {
    throw new Error(`Temporal Mock 格式錯誤：${label} 必須是數字`);
  }
  return value;
}

function normalizeObservation(raw, label) {
  const observation = requireObject(raw, label);
  return {
    timestamp: requireOffsetTimestamp(observation.timestamp, `${label}.timestamp`),
    availableBikes: requireFiniteNumber(
      observation.available_bikes,
      `${label}.available_bikes`,
    ),
    availableDocks: requireFiniteNumber(
      observation.available_docks,
      `${label}.available_docks`,
    ),
  };
}

function normalizeForecast(raw, offsetMinutes, stationId) {
  if (!raw || raw.available === false) {
    return {
      offsetMinutes,
      isAvailable: false,
      reason: raw?.reason || `Mock 未提供 +${offsetMinutes} 展示值`,
    };
  }

  const forecast = requireObject(raw, `${stationId}.fixed_forecasts.+${offsetMinutes}`);
  return {
    offsetMinutes,
    isAvailable: true,
    timestamp: requireOffsetTimestamp(
      forecast.timestamp,
      `${stationId}.fixed_forecasts.+${offsetMinutes}.timestamp`,
    ),
    availableBikes: requireFiniteNumber(
      forecast.available_bikes,
      `${stationId}.fixed_forecasts.+${offsetMinutes}.available_bikes`,
    ),
    lowerBound: requireFiniteNumber(
      forecast.lower_bound,
      `${stationId}.fixed_forecasts.+${offsetMinutes}.lower_bound`,
    ),
    upperBound: requireFiniteNumber(
      forecast.upper_bound,
      `${stationId}.fixed_forecasts.+${offsetMinutes}.upper_bound`,
    ),
  };
}

function normalizeStation(raw) {
  const station = requireObject(raw, "stations[]");
  if (!station.station_id || !station.station_name) {
    throw new Error("Temporal Mock 格式錯誤：站點缺少 station_id 或 station_name");
  }

  const rawForecasts = requireArray(
    station.fixed_forecasts,
    `${station.station_id}.fixed_forecasts`,
  );

  return {
    stationId: station.station_id,
    stationName: station.station_name,
    past: requireArray(station.past, `${station.station_id}.past`).map(
      (item, index) =>
        normalizeObservation(item, `${station.station_id}.past[${index}]`),
    ),
    live: normalizeObservation(station.live, `${station.station_id}.live`),
    forecasts: FIXED_OFFSETS.map((offsetMinutes) =>
      normalizeForecast(
        rawForecasts.find((item) => item.offset_minutes === offsetMinutes),
        offsetMinutes,
        station.station_id,
      ),
    ),
  };
}

export function loadTemporalPresentation() {
  const fixture = requireObject(temporalFixture, "root");
  if (fixture.scope !== "frontend-local-demo") {
    throw new Error("Temporal Mock 格式錯誤：scope 必須是 frontend-local-demo");
  }

  return {
    timezone: fixture.timezone,
    stations: requireArray(fixture.stations, "stations").map(normalizeStation),
  };
}
