// ADR-314：主底圖（OpenFreeMap vector tiles）載入失敗時的 raster 備案底圖。
// raster PNG 圖磚比 vector tiles 輕、相容性好、CDN 分佈廣，在不穩網路下更容易載出來；
// 公開、無金鑰，前端直連。用 OpenStreetMap 官方 raster tile 服務。
import { palettes } from "../theme/palettes.js";

// OSM 官方 raster tile（無金鑰）。三個子網域分流，符合其使用條款（低流量、demo 用途）。
export const RASTER_TILE_ORIGINS = Object.freeze([
  "https://a.tile.openstreetmap.org",
  "https://b.tile.openstreetmap.org",
  "https://c.tile.openstreetmap.org",
]);

export function createRasterBasemapStyle(mode = "light") {
  const bg = (palettes[mode] ?? palettes.light).map.background;
  return {
    version: 8,
    name: "YouBike raster fallback",
    // glyphs/sprite 省略：raster 底圖不需要向量字型/圖示，減少外部資源依賴。
    sources: {
      "osm-raster": {
        type: "raster",
        tiles: RASTER_TILE_ORIGINS.map((o) => `${o}/{z}/{x}/{y}.png`),
        tileSize: 256,
        maxzoom: 19,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [
      // 底色（raster 未載到前先有色塊，避免閃白）
      { id: "raster-bg", type: "background", paint: { "background-color": bg } },
      {
        id: "osm-raster-layer",
        type: "raster",
        source: "osm-raster",
        // 夜間模式把街道圖稍微壓暗，貼近整體暗色調（deck.gl 站點層仍清楚）
        paint: mode === "dark" ? { "raster-brightness-max": 0.6, "raster-saturation": -0.3 } : {},
      },
    ],
  };
}
