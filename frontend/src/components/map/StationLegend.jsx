import { ThunderboltFilled } from "@ant-design/icons";
import presentationConfig from "../../config/presentation.json";
import { getStationPinIcon } from "../../utils/stationPinIcon.js";
import { rentalLabels } from "../../utils/stationAppearance.js";

export default function StationLegend({ dimension = "status" }) {
  if (dimension === "usage") return <div className="station-legend" aria-label="可借比例圖例">
    <span className="station-legend-note">可借比例</span>
    {presentationConfig.usageBands.map((band, i) => <span key={band.max} className="station-legend-item">
      <span style={{ width: 9, height: 9, borderRadius: 3, background: band.color }} />
      {i === 0 ? "0–10%" : i === 4 ? ">99.9%" : `${presentationConfig.usageBands[i - 1].max}–${band.max}%`}
    </span>)}
  </div>;
  return <div className="station-legend" aria-label="YouBike 站點狀態圖例">
    {["normal", "empty", "full", "offline"].map(status => <span className="station-legend-item" key={status}>
      <img src={getStationPinIcon(.5, presentationConfig.statusColors[status]).url} alt="" />{rentalLabels[status]}
    </span>)}
    <span className="station-legend-item"><span className="electric-key"><ThunderboltFilled /></span>電輔車</span>
    <span className="station-legend-note">弧線多寡＝可借比例</span>
  </div>;
}
