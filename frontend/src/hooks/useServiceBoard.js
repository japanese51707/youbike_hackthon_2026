import { useCallback, useEffect } from "react";
import { fetchBackendStations } from "../api/backendStations.js";
import { request } from "../api/httpClient.js";
import useAsyncResource from "./useAsyncResource.js";

const POLL_MS = 60_000;

async function loadServiceBoard() {
  const [kpi, stations, overview, problems] = await Promise.all([
    request("/kpi"),
    fetchBackendStations(),
    request("/dispatch/overview"),
    request("/service-problems").catch(() => ({ city: {}, open: [], districts: [] })),
  ]);
  return { kpi, stations, overview, problems, fetchedAt: Date.now() };
}

export default function useServiceBoard() {
  const loader = useCallback(() => loadServiceBoard(), []);
  const resource = useAsyncResource(loader);
  useEffect(() => {
    const timer = setInterval(() => resource.reload({ silent: true }).catch(() => {}), POLL_MS);
    return () => clearInterval(timer);
  }, [resource.reload]);
  return resource;
}
