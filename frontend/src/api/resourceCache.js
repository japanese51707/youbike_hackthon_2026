// 前端讀取暫存：切頁卸載後仍留在模組記憶體，回來先畫上一筆，再背景更新。
// 不進 sessionStorage／localStorage，重整才清空；也不冒充 mock。

const values = new Map();
const inflight = new Map();

export function peekResource(key) {
  return values.get(key)?.data ?? null;
}

export function rememberResource(key, data) {
  if (data == null) return data;
  values.set(key, { data, at: Date.now() });
  return data;
}

export function clearResourceCache(key) {
  if (key) {
    values.delete(key);
    inflight.delete(key);
    return;
  }
  values.clear();
  inflight.clear();
}

export async function cachedRead(key, loader, { ttlMs = 60_000, bypass = false, keepOnError = true } = {}) {
  const hit = values.get(key);
  if (!bypass && hit && Date.now() - hit.at < ttlMs) return hit.data;
  if (inflight.has(key)) return inflight.get(key);

  const pending = Promise.resolve()
    .then(loader)
    .then((data) => {
      rememberResource(key, data);
      return data;
    })
    .catch((error) => {
      if (keepOnError && hit?.data != null) return hit.data;
      throw error;
    })
    .finally(() => {
      inflight.delete(key);
    });

  inflight.set(key, pending);
  return pending;
}
