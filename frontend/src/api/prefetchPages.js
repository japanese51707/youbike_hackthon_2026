// 進站後先暖全市站況，再慢慢預取其他分頁。
// 不可一次並行全打：瀏覽器同網域連線有限，官方 CSV 一慢，20 秒逾時會讓所有頁一起失敗。
import { getAssignedWorkspace } from "./taskApi.js";
import { getDailyReview } from "./optimizationApi.js";
import { getDashboardData } from "./stationsApi.js";
import { getDriverWorkspace } from "./driverApi.js";
import { getEscalationHistory } from "./escalationApi.js";
import { getOperationsOverview } from "./operationsApi.js";
import { fetchBackendStations } from "./backendStations.js";
import { getActorId, isApiMode, request } from "./httpClient.js";
import { rememberResource } from "./resourceCache.js";
import { prefetchServiceBoard } from "./serviceBoardApi.js";

let pending = null;

function swallow(promise) {
  return promise.then(() => undefined, () => undefined);
}

async function runSerial(jobs) {
  for (const job of jobs) {
    await swallow(job());
  }
}

async function prefetchDriver() {
  if (!isApiMode) {
    const workspace = await getDriverWorkspace();
    rememberResource("driver-workspace", workspace);
    return;
  }
  const actor = getActorId();
  if (!actor) return;
  const workspace = await getAssignedWorkspace(actor);
  rememberResource(`driver-assigned:${actor}`, workspace);
}

async function runPrefetch() {
  await swallow(fetchBackendStations());
  await runSerial([
    () => getDashboardData(),
    () => getDashboardData({ lite: true }),
    () => prefetchServiceBoard(),
    () => getOperationsOverview().then((overview) => {
      rememberResource("dispatch-status", overview);
      rememberResource("operations-overview", overview);
    }),
    () => getEscalationHistory(100).then((rows) => rememberResource("escalation-history", rows)),
    () => (isApiMode ? getDailyReview().then((review) => rememberResource("daily-review", review)) : Promise.resolve()),
    () => prefetchDriver(),
    () => (isApiMode
      ? request("/stations/timeline?district=全市&date=2026-06-02").then((payload) => {
        rememberResource("twin-timeline", payload);
      })
      : Promise.resolve()),
  ]);
}

export function prefetchAllPages() {
  if (!pending) pending = runPrefetch();
  return pending;
}
