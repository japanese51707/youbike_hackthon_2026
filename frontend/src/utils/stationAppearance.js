// 官方參考圖的「租借狀態」與調度緊急度各自呈現；不改後端 status 或規則。
export function getRentalStatus(station) {
  if (station.service_available === false || station.status === "offline") return "offline";
  if (["empty", "full"].includes(station.status)) return station.status;
  if (["low", "normal", "high"].includes(station.status)) return "normal";
  return "unknown";
}
export const rentalLabels = {
  normal: "正常租借", empty: "無車可借", full: "車位滿載", offline: "暫停營運", unknown: "站況未確認",
};
// 現行共同契約未提供電輔車數：只接受明確的可借數，缺值／字串／容量不可推測。
export function hasAvailableElectricBike(station) {
  return station.service_available !== false && ["low", "normal", "high", "full"].includes(station.status)
    && typeof station.available_electric_bikes === "number"
    && Number.isFinite(station.available_electric_bikes) && station.available_electric_bikes > 0;
}
