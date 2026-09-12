/**
 * 調度卡片的文案去重：同一件事只講一次。
 *
 * 卡片上有三段可能互相重複的文字：
 *   標題（站名）／警報訊息（怎麼了）／建議原因（為什麼要派）
 * 後端這三段各自獨立產生，實務上常常：
 *   1. 警報訊息開頭又寫一次站名；
 *   2. 警報訊息與建議原因講同一件事，只差幾個數字
 *      （例：「現況 6 台，30 分鐘後…」vs「現況 1 台，30 分鐘後…」）。
 * 這裡不改後端語意，只在呈現層把重複的那一段收掉。
 */

const LEADING_SEPARATORS = /^[\s｜|、,，:：・·—-]+/;

/** 拿掉開頭重複的站名（標題已經顯示過）。 */
export function stripStationName(text, stationName) {
  const value = (text ?? "").trim();
  if (!value || !stationName) return value;
  return value.startsWith(stationName)
    ? value.slice(stationName.length).replace(LEADING_SEPARATORS, "")
    : value;
}

const squash = (text) => (text ?? "").replace(/\s/g, "");

/** 字元二元組的 Dice 係數（0~1）；中文不分詞也能用。 */
export function similarity(a, b) {
  const x = squash(a);
  const y = squash(b);
  if (!x || !y) return 0;
  if (x === y) return 1;
  if (x.length < 2 || y.length < 2) return x === y ? 1 : 0;
  const grams = (s) => {
    const map = new Map();
    for (let i = 0; i < s.length - 1; i += 1) {
      const g = s.slice(i, i + 2);
      map.set(g, (map.get(g) ?? 0) + 1);
    }
    return map;
  };
  const ga = grams(x);
  const gb = grams(y);
  let shared = 0;
  let total = 0;
  for (const [g, count] of ga) {
    total += count;
    if (gb.has(g)) shared += Math.min(count, gb.get(g));
  }
  for (const [, count] of gb) total += count;
  return total ? (2 * shared) / total : 0;
}

/**
 * 兩句話是不是在講同一件事。
 * 完全包含（只是多了前綴）或高度相似（只差幾個數字）都算重複。
 */
export function isSameMessage(a, b, threshold = 0.7) {
  const x = squash(a);
  const y = squash(b);
  if (!x || !y) return false;
  if (x.includes(y) || y.includes(x)) return true;
  return similarity(x, y) >= threshold;
}
