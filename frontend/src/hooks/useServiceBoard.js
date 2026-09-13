import { useCallback, useEffect, useRef } from "react";
import { EMPTY_PROBLEMS, SERVICE_BOARD_CACHE_KEY, loadServiceBoard } from "../api/serviceBoardApi.js";
import useAsyncResource from "./useAsyncResource.js";

const POLL_MS = 60_000;

export default function useServiceBoard() {
  const lastProblemsRef = useRef(null);
  const loader = useCallback(async () => {
    const data = await loadServiceBoard(lastProblemsRef.current);
    if (data.problems && data.problems !== lastProblemsRef.current) {
      lastProblemsRef.current = data.problems;
    }
    return data;
  }, []);
  const resource = useAsyncResource(loader, { cacheKey: SERVICE_BOARD_CACHE_KEY });
  useEffect(() => {
    const cached = resource.data;
    if (cached?.problems && cached.problems !== EMPTY_PROBLEMS) {
      lastProblemsRef.current = cached.problems;
    }
  }, [resource.data]);
  useEffect(() => {
    const timer = setInterval(() => resource.reload({ silent: true }).catch(() => {}), POLL_MS);
    return () => clearInterval(timer);
  }, [resource.reload]);
  return resource;
}
