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
