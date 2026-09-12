import { haversineKm } from "./geo.js";

// 在折線上找最接近某點的頂點，用來把實走道路切成「站與站」各段。
export function nearestVertexIndex(path, lng, lat) {
  let bestIndex = 0;
  let best = Infinity;
  for (let i = 0; i < path.length; i += 1) {
    const dx = path[i][0] - lng;
    const dy = path[i][1] - lat;
    const distance = dx * dx + dy * dy;
    if (distance < best) {
      best = distance;
      bestIndex = i;
    }
  }
  return bestIndex;
}

// 依途經點把一條折線切成連續路段。途經點對不到線上時，退回兩點直線。
export function splitPathByWaypoints(path, waypoints) {
  if (!Array.isArray(path) || path.length < 2) return [];
  if (!Array.isArray(waypoints) || waypoints.length < 2) return [];

  const cuts = waypoints.map((point) => nearestVertexIndex(path, point.lng, point.lat));
  for (let i = 1; i < cuts.length; i += 1) {
    cuts[i] = Math.max(cuts[i], cuts[i - 1]);
  }

  const legs = [];
  for (let i = 0; i < cuts.length - 1; i += 1) {
    const slice = path.slice(cuts[i], cuts[i + 1] + 1);
    if (slice.length >= 2) {
      legs.push(slice);
      continue;
    }
    legs.push([
      [waypoints[i].lng, waypoints[i].lat],
      [waypoints[i + 1].lng, waypoints[i + 1].lat],
    ]);
  }
  return legs;
}

export function joinPaths(paths) {
  const out = [];
  for (const path of paths) {
    if (!path?.length) continue;
    if (!out.length) {
      out.push(...path);
      continue;
    }
    const last = out[out.length - 1];
    const first = path[0];
    const same = last[0] === first[0] && last[1] === first[1];
    out.push(...(same ? path.slice(1) : path));
  }
  return out;
}

// 把折線拆成短劃，給 PathLayer 當虛線用（不必加 deck.gl extensions）。
export function dashSegments(path, dashKm = 0.036, gapKm = 0.026) {
  if (!Array.isArray(path) || path.length < 2) return [];
  if (!(dashKm > 0) || !(gapKm > 0)) return [path];

  const segments = [];
  let drawing = true;
  let remainingBudget = dashKm;
  let current = [path[0]];
  let cursor = path[0];

  const flip = () => {
    if (drawing && current.length >= 2) segments.push(current);
    drawing = !drawing;
    remainingBudget = drawing ? dashKm : gapKm;
    current = drawing ? [cursor] : [];
  };

  for (let i = 1; i < path.length; i += 1) {
    const dest = path[i];
    let from = cursor;
    let edgeLeft = haversineKm(
      { lng: from[0], lat: from[1] },
      { lng: dest[0], lat: dest[1] },
    );
    if (!Number.isFinite(edgeLeft) || edgeLeft < 1e-8) {
      cursor = dest;
      continue;
    }
    while (edgeLeft > 1e-8) {
      const take = Math.min(edgeLeft, remainingBudget);
      const ratio = take / edgeLeft;
      const next = [from[0] + (dest[0] - from[0]) * ratio, from[1] + (dest[1] - from[1]) * ratio];
      if (drawing) current.push(next);
      from = next;
      cursor = next;
      edgeLeft -= take;
      remainingBudget -= take;
      if (remainingBudget <= 1e-8) flip();
    }
    cursor = dest;
  }
  if (drawing && current.length >= 2) segments.push(current);
  return segments;
}
