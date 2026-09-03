// 共用地圖遠端邊界：底圖 style 改為自帶暗色 style（ADR-014），
// 但所有 tile／glyph／sprite 仍鎖 OpenFreeMap 同源；此處集中出向 allowlist 與 attribution。
export const mapConfig = Object.freeze({
  // 僅作為 origin allowlist 與相對 URL 解析的基準；實際 style 由 createDarkBasemapStyle() 提供。
  styleBaseUrl: "https://tiles.openfreemap.org/",
  allowedOrigins: Object.freeze(["https://tiles.openfreemap.org"]),
  styleLoadTimeoutMs: 15000,
  resourceLoadTimeoutMs: 30000,
  resourceErrorThreshold: 3,
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
