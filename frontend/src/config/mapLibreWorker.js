import * as maplibregl from "maplibre-gl";
// MapLibre GL v6 的 worker 是獨立 ESM，Vite 無法自動解析其 worker/shared chunk URL；
// 用 ?worker&url 讓 Vite 產出可被 fetch 的 worker asset，並在建立任何 Map 前設定一次。
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";

let configured = false;

// 對外只暴露一次性的 worker URL 設定；重複呼叫為 no-op。
export function configureMapLibreWorker() {
  if (configured) return;
  maplibregl.setWorkerUrl(maplibreWorkerUrl);
  configured = true;
}
