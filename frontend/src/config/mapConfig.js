// 共用地圖遠端邊界：只允許 ADR-012 核准的 OpenFreeMap style 與其同源資源。
export const mapConfig = Object.freeze({
  styleUrl: "https://tiles.openfreemap.org/styles/liberty",
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
    const requestUrl = new URL(url, mapConfig.styleUrl);
    return (
      requestUrl.protocol === "https:" &&
      mapConfig.allowedOrigins.includes(requestUrl.origin)
    );
  } catch {
    return false;
  }
}
