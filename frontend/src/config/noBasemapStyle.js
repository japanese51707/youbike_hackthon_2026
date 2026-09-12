import { palettes } from "../theme/palettes.js";
// 本地 empty style 不含 source、tile、glyph 或 sprite；遠端底圖失敗時仍可承載 Deck.gl layers。
export function createNoBasemapStyle(mode = "light") {
  return {
    version: 8,
    name: "YouBike no-basemap",
    sources: {},
    layers: [
      {
        id: "no-basemap-background",
        type: "background",
        paint: { "background-color": (palettes[mode] ?? palettes.light).map.background },
      },
    ],
  };
}
