import catalog from "../data/newtaipeiDistricts.json" with { type: "json" };

const cache = new Map();

function bboxCenter(multi) {
  let minLng = Infinity;
  let minLat = Infinity;
  let maxLng = -Infinity;
  let maxLat = -Infinity;
  for (const polygon of multi ?? []) {
    const rings = Array.isArray(polygon[0]?.[0]) ? polygon : [polygon];
    for (const ring of rings) {
      for (const point of ring) {
        const lng = Number(point?.[0]);
        const lat = Number(point?.[1]);
        if (!Number.isFinite(lng) || !Number.isFinite(lat)) continue;
        minLng = Math.min(minLng, lng);
        minLat = Math.min(minLat, lat);
        maxLng = Math.max(maxLng, lng);
        maxLat = Math.max(maxLat, lat);
      }
    }
  }
  if (!Number.isFinite(minLng)) return null;
  return {
    lng: Math.round(((minLng + maxLng) / 2) * 1e5) / 1e5,
    lat: Math.round(((minLat + maxLat) / 2) * 1e5) / 1e5,
  };
}

/** 行政區邊界框中心。車／人沒有 GPS 時當司機地圖出發點，才畫得出路線。 */
export function districtCenter(district) {
  if (!district) return null;
  if (cache.has(district)) return cache.get(district);
  const center = bboxCenter(catalog.polygons?.[district]);
  cache.set(district, center);
  return center;
}
