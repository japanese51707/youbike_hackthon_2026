// ADR-208：依使用者提供的官方站點參考圖，以 SVG 繪製水滴圖釘與弧線。
// 保留向量清晰度；有限色票 × 3 檔弧線 × 電輔旗標快取，不逐站產生畫布。
const cache = new Map();
export function getStationPinIcon(ratio, color, electric = false) {
  const safeColor = /^#[0-9a-f]{6}$/i.test(color) ? color : "#858783";
  const safeRatio = Number.isFinite(ratio) ? Math.max(0, Math.min(1, ratio)) : 0;
  const arcs = safeRatio > 2 / 3 ? 3 : safeRatio > 1 / 3 ? 2 : 1;
  const id = `pin-${safeColor}-${arcs}-${Boolean(electric)}`;
  if (!cache.has(id)) {
    const signals = [
      '<path d="M28 32a8 8 0 0 1 8 8"/>',
      '<path d="M28 24a16 16 0 0 1 16 16"/>',
      '<path d="M28 16a24 24 0 0 1 24 24"/>',
    ].slice(0, arcs).join("");
    const badge = electric ? '<circle cx="15" cy="16" r="13" fill="#ae2828" stroke="white" stroke-width="2.5"/><path d="m18 6-11 13h7l-3 9 12-15h-7z" fill="white"/>' : "";
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="80" viewBox="0 0 64 80"><path d="M35 75 27 56C15 52 10 43 10 30a25 25 0 0 1 50 0c0 13-5 22-17 26Z" fill="${safeColor}" stroke="white" stroke-width="2.5" stroke-linejoin="round"/><g fill="none" stroke="white" stroke-width="4.3" stroke-linecap="round" transform="translate(-3 -2)">${signals}</g>${badge}</svg>`;
    cache.set(id, { id, url: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`, width: 64, height: 80, anchorX: 35, anchorY: 75, mask: false });
  }
  return cache.get(id);
}
