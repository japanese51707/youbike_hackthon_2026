import { fetchBackendStations } from "./backendStations.js";
import { request } from "./httpClient.js";
import { getOperationsOverview } from "./operationsApi.js";
import { peekResource, rememberResource } from "./resourceCache.js";
import { kpiFromStations } from "../utils/serviceBoard.js";

export const SERVICE_BOARD_CACHE_KEY = "service-board";
export const EMPTY_PROBLEMS = { city: {}, open: [], districts: [] };

const STATION_BOUND_MS = 45_000;

let inflight = null;

async function loadServiceBoardOnce(previousProblems) {
  // 先拿站況：官方 CSV 可能 20–45 秒。/kpi 也走同一份快照，先等站況才打可避開 20 秒逾時。
  const stations = await fetchBackendStations();
  const [kpi, overview, problems] = await Promise.all([
    request("/kpi", { timeoutMs: STATION_BOUND_MS }).catch(() => kpiFromStations(stations)),
    getOperationsOverview().catch(() => ({})),
    request("/service-problems", { timeoutMs: STATION_BOUND_MS })
      .catch(() => previousProblems ?? EMPTY_PROBLEMS),
  ]);
  return {
    kpi: kpi ?? kpiFromStations(stations),
    stations,
    overview,
    problems,
    fetchedAt: Date.now(),
  };
}

export function loadServiceBoard(previousProblems) {
  if (inflight) return inflight;
  inflight = loadServiceBoardOnce(previousProblems).finally(() => {
    inflight = null;
  });
  return inflight;
}

export async function prefetchServiceBoard() {
  const previous = peekResource(SERVICE_BOARD_CACHE_KEY);
  const data = await loadServiceBoard(previous?.problems);
  return rememberResource(SERVICE_BOARD_CACHE_KEY, data);
}
