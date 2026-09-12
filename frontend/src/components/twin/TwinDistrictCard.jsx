import { Select } from "antd";
import { CITY_LABEL, CITY_SCOPE, isCityScope } from "../../utils/districtScope.js";

export default function TwinDistrictCard({
  value,
  districts = [],
  stationCount = 0,
  outlineSource,
  onChange,
}) {
  const options = [
    { value: CITY_SCOPE, label: CITY_LABEL },
    ...districts.map((district) => ({ value: district, label: district })),
  ];
  const note = isCityScope(value)
    ? `目前 ${stationCount} 站，解讀與圖層含新北市全區。`
    : outlineSource === "town-boundary"
      ? `紅線為${value}行政區界；圖層與解讀只含該區 ${stationCount} 站。`
      : `紅線為該區站點包絡，非正式地政界線；圖層與解讀只含 ${stationCount} 站。`;

  return (
    <aside className="twin-district" aria-label="限縮行政區">
      <div className="twin-control-title">限縮行政區</div>
      <Select
        showSearch
        value={value}
        onChange={onChange}
        options={options}
        optionFilterProp="label"
        style={{ width: "100%" }}
        popupMatchSelectWidth
      />
      <p className="twin-district-note">{note}</p>
    </aside>
  );
}
