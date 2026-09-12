import { createBasemapStyle } from "../../config/darkBasemapStyle.js";
import { createNoBasemapStyle } from "../../config/noBasemapStyle.js";

// 只改 paint，不呼叫 setStyle／重建 Map：保留視角、資料圖層、選站及載入狀態。
export function applyMapAppearance(map, mode, fallback) {
  const style = fallback ? createNoBasemapStyle(mode) : createBasemapStyle(mode);
  for (const layer of style.layers) {
    if (!map.getLayer(layer.id)) continue;
    for (const [property, value] of Object.entries(layer.paint ?? {})) {
      if (property.endsWith("color")) map.setPaintProperty(layer.id, property, value);
    }
  }
}
