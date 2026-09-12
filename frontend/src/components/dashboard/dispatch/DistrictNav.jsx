import { Typography } from "antd";

/**
 * 調度任務的行政區側邊目錄。
 * 數字＝該行政區在「目前分頁」底下的任務數，所以切分頁時數字跟著換——
 * 看到的數字永遠對應正在看的那份清單，不會是全部任務的總數。
 */
export default function DistrictNav({ counts, value, total, onChange }) {
  const items = [
    { district: "all", count: total, label: "全部" },
    ...counts.map((c) => ({ ...c, label: c.district })),
  ];

  return (
    <nav className="district-nav" aria-label="行政區">
      <div className="district-nav-title">行政區</div>
      <ul className="district-nav-list">
        {items.map((item) => (
          <li key={item.district}>
            <button
              type="button"
              className={`district-nav-item${value === item.district ? " is-active" : ""}`}
              aria-current={value === item.district ? "true" : undefined}
              onClick={() => onChange(item.district)}
            >
              <span className="district-nav-label">{item.label}</span>
              <span className={`district-nav-count mono${item.count ? "" : " is-zero"}`}>
                {item.count}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {counts.length === 0 ? (
        <Typography.Text type="secondary" className="district-nav-empty">
          這個分頁目前沒有任務
        </Typography.Text>
      ) : null}
    </nav>
  );
}
