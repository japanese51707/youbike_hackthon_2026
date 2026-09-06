// 產生「環形進度環」marker 圖示（ADR-204 多維度資產編碼）。
// 弧長 = 可借比例，顏色 = 風險/狀態；以 canvas 產生並快取，維持各 zoom 下像素一致與效能。

const ICON_SIZE = 128;
const cache = new Map();

function roundRatio(ratio) {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(ratio) ? ratio : 0));
  return Math.round(clamped * 20) / 20; // 5% 一階，控制快取數量
}

function drawGauge(ratio, color) {
  const canvas = document.createElement("canvas");
  canvas.width = ICON_SIZE;
  canvas.height = ICON_SIZE;
  const ctx = canvas.getContext("2d");

  const center = ICON_SIZE / 2;
  const radius = 50;
  const thickness = 13;
  const start = -Math.PI / 2; // 從正上方開始

  // 軌道（未填滿部分）
  ctx.beginPath();
  ctx.arc(center, center, radius, 0, Math.PI * 2);
  ctx.strokeStyle = "rgba(148, 163, 184, 0.28)";
  ctx.lineWidth = thickness;
  ctx.stroke();

  // 數值弧（可借比例）
  if (ratio > 0) {
    ctx.beginPath();
    ctx.arc(center, center, radius, start, start + Math.PI * 2 * ratio);
    ctx.strokeStyle = color;
    ctx.lineWidth = thickness;
    ctx.lineCap = "round";
    ctx.shadowColor = color;
    ctx.shadowBlur = 12;
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // 中心狀態核心
  ctx.beginPath();
  ctx.arc(center, center, 24, 0, Math.PI * 2);
  ctx.fillStyle = color;
  ctx.globalAlpha = 0.92;
  ctx.fill();
  ctx.globalAlpha = 1;
  ctx.lineWidth = 2.5;
  ctx.strokeStyle = "rgba(5, 7, 13, 0.85)";
  ctx.stroke();

  return canvas.toDataURL("image/png");
}

export function getGaugeIcon(ratio, color) {
  const bucket = roundRatio(ratio);
  const id = `${color}|${bucket}`;
  let url = cache.get(id);
  if (!url) {
    url = drawGauge(bucket, color);
    cache.set(id, url);
  }
  return {
    id,
    url,
    width: ICON_SIZE,
    height: ICON_SIZE,
    anchorX: ICON_SIZE / 2,
    anchorY: ICON_SIZE / 2,
    mask: false,
  };
}
