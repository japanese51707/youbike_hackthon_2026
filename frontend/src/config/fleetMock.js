// 調度路線規劃（示意 Mock）參數（ADR-004：真實最佳化屬後端 rule-engine，本檔僅供前端示意）。
// 參數外部化，方便 Demo 現場調整；不改後端契約，也不進派遣 payload。
export const fleetPlannerConfig = Object.freeze({
  serviceRadiusKm: 5, // 每台載具的服務半徑
  maxStops: 6, // 單條示意路線最多停靠點
  targetRatio: 0.5, // 站點目標水位（佔容量比例），用於估算取/補數量
  vehicleColor: [102, 217, 232], // 載具標記
  stopPickupColor: [255, 169, 77], // 取車
  stopDropoffColor: [56, 217, 169], // 補車
});

// 互動式組單（ADR-119 三入口）示意參數。真正最優組單在後端 dispatch_builder，
// 這裡只做確定性、可追溯的示意排序，不進派遣 payload、不改後端契約。
export const tripPlannerConfig = Object.freeze({
  fallbackCapacity: 15, // 車輛主檔未指定 max_capacity 時的載運上限（對齊 ADR-114）
  avgSpeedKmh: 20, // 市區示意平均車速（估交通時間）
  perStopMinutes: 5, // 每站示意作業時間（取/放）
  targetRatio: 0.5, // 站點目標水位（佔容量比例），估取/補數量
  maxPickups: 3, // 單趟最多取車站
  maxDropoffs: 4, // 單趟最多補車站
});
