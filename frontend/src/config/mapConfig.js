// 共用地圖遠端邊界：底圖使用自帶日夜 style（ADR-208），
// 但所有 tile／glyph／sprite 仍鎖 OpenFreeMap 同源；此處集中出向 allowlist 與 attribution。
export const mapConfig = Object.freeze({
  // 僅作為 origin allowlist 與相對 URL 解析的基準；實際 style 由 createBasemapStyle() 提供。
  styleBaseUrl: "https://tiles.openfreemap.org/",
  // ADR-314：主底圖 OpenFreeMap + raster 備案 OSM 官方 tile（皆公開無金鑰，前端直連）。
  allowedOrigins: Object.freeze([
    "https://tiles.openfreemap.org",
    "https://a.tile.openstreetmap.org",
    "https://b.tile.openstreetmap.org",
    "https://c.tile.openstreetmap.org",
  ]),
  // ADR-314：放寬逾時/錯誤門檻，給現場網路較慢時更多時間載主底圖，別太快就 fallback。
  styleLoadTimeoutMs: 30000,        // 15s → 30s
  resourceLoadTimeoutMs: 45000,     // 30s → 45s
  resourceErrorThreshold: 6,        // 3 → 6（連續 6 次資源錯誤才 fallback）
  resourceErrorWindowMs: 5000,
  providerName: "OpenFreeMap",
  providerUrl: "https://openfreemap.org/",
  attribution: Object.freeze([
    Object.freeze({ label: "© OpenFreeMap", url: "https://openfreemap.org/" }),
    Object.freeze({ label: "© OpenMapTiles", url: "https://www.openmaptiles.org/" }),
    Object.freeze({
      label: "© OpenStreetMap contributors",
      url: "https://www.openstreetmap.org/copyright",
    }),
  ]),
});

export function isAllowedBasemapRequest(url) {
  try {
    const requestUrl = new URL(url, mapConfig.styleBaseUrl);
    return (
      requestUrl.protocol === "https:" &&
      mapConfig.allowedOrigins.includes(requestUrl.origin)
    );
  } catch {
    return false;
  }
}
