// ADR-208：品牌、介面與圖表色票；站況色獨立存於 presentation.json。
export const THEME_STORAGE_KEY = "youbike-appearance";
export const palettes = {
  light: {
    bg: "#f7f6f0", bgSoft: "#f2f0e8", panel: "#fffefa", panel2: "#f7f5ed",
    border: "#dedbd0", text: "#343830", muted: "#666a5e", primary: "#9b5708",
    accent: "#fa9412", yellow: "#fff000", onAccent: "#352705",
    danger: "#b8342b", warning: "#9b5708", success: "#527b2f", info: "#396e79",
    primarySoft: "#fff2da", dangerSoft: "#fff0ec", infoSoft: "#eaf1f2",
    grid: "#e5e2d8", line: "#b56a12", band: "rgba(220,151,51,0.18)",
    overlay: "rgba(255,254,250,0.96)", shadow: "rgba(57,48,27,0.07)",
    map: { background: "#f1efe5", water: "#ccdedb", waterway: "#b0cdca", park: "#dce6cc", wood: "#d1dfc4", building: "#e5e1d6", buildingOutline: "#dad5c7", roadCasing: "#ddd6c4", roadMinor: "#fffdf6", roadMajor: "#fffdf4", motorway: "#e7cb91", boundary: "#b9b5a6", label: "#64695b", labelHalo: "#f9f7f0", waterLabel: "#527c7b" },
  },
  dark: {
    bg: "#20231f", bgSoft: "#272b24", panel: "#2b2f28", panel2: "#32362e",
    border: "#45493c", text: "#eeeede", muted: "#b4b7a7", primary: "#f3c56f",
    accent: "#f2b354", yellow: "#e4cf64", onAccent: "#30270f",
    danger: "#f18c7f", warning: "#efbc72", success: "#b0cb86", info: "#9fc4ca",
    primarySoft: "#393425", dangerSoft: "#3d2c26", infoSoft: "#2b3837",
    grid: "#44483c", line: "#f2c575", band: "rgba(242,197,117,0.18)",
    overlay: "rgba(43,47,40,0.96)", shadow: "rgba(0,0,0,0.16)",
    map: { background: "#252922", water: "#2e4341", waterway: "#3e5752", park: "#35432c", wood: "#33412b", building: "#30352b", buildingOutline: "#3e4437", roadCasing: "#23271f", roadMinor: "#424737", roadMajor: "#62654c", motorway: "#8c8058", boundary: "#777664", label: "#c3c4af", labelHalo: "#252922", waterLabel: "#9abdb4" },
  },
};
export function resolveAppearance(preference, systemDark) {
  return preference === "dark" || (preference === "system" && systemDark) ? "dark" : "light";
}
export function validAppearance(value) {
  return ["light", "dark", "system"].includes(value) ? value : "system";
}
