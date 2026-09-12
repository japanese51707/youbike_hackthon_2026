import { Tag, Typography } from "antd";

const DATA_MODE_TAG = {
  real: { color: "green", text: "實算" },
  method: { color: "gold", text: "方法展示" },
  pending: { color: "default", text: "待接資料" },
};

function formatMetric(metric) {
  if (metric.value == null || metric.value === "") return "—";
  return metric.unit ? `${metric.value} ${metric.unit}` : String(metric.value);
}

export default function TwinInsightPanel({
  report,
  loading,
  error,
  onSelectStation,
  onSelectLayer,
}) {
  if (loading) {
    return (
      <aside className="twin-insight" aria-label="當前解讀">
        <div className="twin-control-title">當前解讀</div>
        <Typography.Text type="secondary">站況載入中…</Typography.Text>
      </aside>
    );
  }

  if (error) {
    return (
      <aside className="twin-insight" aria-label="當前解讀">
        <div className="twin-control-title">當前解讀</div>
        <Typography.Text type="danger">{error.message || "站況載入失敗"}</Typography.Text>
      </aside>
    );
  }

  if (!report) return null;

  return (
    <aside className="twin-insight" aria-label="當前解讀">
      <div className="twin-control-title">當前解讀</div>
      <div className="twin-insight-meta">
        <span>{report.nStations} 站</span>
        <span>{report.stationsSource === "backend" ? "後端站況" : report.stationsSource || "來源不明"}</span>
        {report.observedAt ? <span className="mono">{report.observedAt}</span> : null}
      </div>

      {!report.cityWideOk && report.gateReason ? (
        <div className="twin-insight-gate">{report.gateReason}</div>
      ) : null}

      {report.headline ? <p className="twin-insight-headline">{report.headline}</p> : null}

      {report.layers.length === 0 ? (
        <Typography.Text type="secondary">先勾選左側圖層，才會產出對應指標與結論。</Typography.Text>
      ) : null}

      {report.layers.map((layer) => {
        const tag = DATA_MODE_TAG[layer.dataMode] ?? DATA_MODE_TAG.method;
        return (
          <section key={layer.key} className="twin-insight-card">
            <button type="button" className="twin-insight-card-head" onClick={() => onSelectLayer?.(layer.key)}>
              <strong>{layer.title}</strong>
              <Tag color={tag.color} className="twin-mode-tag">{tag.text}</Tag>
            </button>

            {layer.metrics.length ? (
              <div className="twin-insight-metrics">
                {layer.metrics.map((metric) => (
                  <div key={metric.label} className="twin-insight-metric">
                    <span>{metric.label}</span>
                    <b className="mono">{formatMetric(metric)}</b>
                  </div>
                ))}
              </div>
            ) : null}

            {layer.findings.map((line) => (
              <p key={line} className="twin-insight-finding">{line}</p>
            ))}

            {layer.evidence?.length ? (
              <ul className="twin-insight-evidence">
                {layer.evidence.map((item) => {
                  const clickable = Boolean(item.station_id && onSelectStation);
                  const key = item.station_id || item.label;
                  return (
                    <li key={key}>
                      {clickable ? (
                        <button type="button" onClick={() => onSelectStation(item.station_id)}>
                          {item.label}
                          <span>{item.detail}</span>
                        </button>
                      ) : (
                        <span>
                          {item.label}
                          <span>{item.detail}</span>
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : null}

            {layer.caveats.map((line) => (
              <p key={line} className="twin-insight-caveat">{line}</p>
            ))}
          </section>
        );
      })}

      <p className="twin-insight-footnote">本頁只解釋地圖，不產生派工指令。</p>
    </aside>
  );
}
