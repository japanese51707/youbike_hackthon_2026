import { PolygonLayer } from "@deck.gl/layers";

// 紅線框選目前限縮的行政區。優先用鄉鎮區界；沒有圖資時才畫站點包絡。
export function createDistrictOutlineLayer(outline, id = "district-outline") {
  if (!outline?.polygons?.length) return null;
  const data = outline.polygons.map((polygon, index) => ({
    id: `${outline.district}-${index}`,
    name: outline.district,
    polygon,
  }));
  return new PolygonLayer({
    id,
    data,
    stroked: true,
    filled: true,
    extruded: false,
    getPolygon: (row) => row.polygon,
    getFillColor: [220, 38, 38, 22],
    getLineColor: [220, 38, 38, 235],
    getLineWidth: 2.5,
    lineWidthMinPixels: 2,
    lineWidthUnits: "pixels",
    pickable: false,
    parameters: { depthTest: false },
  });
}
