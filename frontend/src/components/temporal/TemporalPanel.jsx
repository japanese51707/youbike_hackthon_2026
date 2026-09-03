import { Alert, Card, Empty, Segmented, Select, Space, Tag, Typography } from "antd";
import useTemporalPresentation from "../../hooks/useTemporalPresentation.js";
import { formatDateTime } from "../../utils/formatters.js";

const modeOptions = [
  { value: "past", label: "Past" },
  { value: "live", label: "Live" },
  { value: "predict", label: "Predict" },
];

function ObservationValue({ label, mode, selectedMode, value, note }) {
  const isUnavailable = !value;
  return (
    <section
      className={[
        "temporal-value",
        mode === selectedMode ? "temporal-value-active" : "",
        isUnavailable ? "temporal-value-unavailable" : "",
      ].filter(Boolean).join(" ")}
    >
      <Tag>{label}</Tag>
      {value ? (
        <>
          <Typography.Title level={5}>可借 {value.availableBikes} 台</Typography.Title>
          <Typography.Text>可還 {value.availableDocks} 位</Typography.Text>
          <br />
          <Typography.Text type="secondary">{formatDateTime(value.timestamp)}</Typography.Text>
          {note ? <><br /><Typography.Text type="secondary">{note}</Typography.Text></> : null}
        </>
      ) : (
        <Typography.Paragraph>不可用</Typography.Paragraph>
      )}
    </section>
  );
}

function ForecastValue({ forecast }) {
  return (
    <div className={forecast.isAvailable ? "" : "temporal-value-unavailable"}>
      <Tag color={forecast.isAvailable ? "purple" : "default"}>
        +{forecast.offsetMinutes}
      </Tag>
      {forecast.isAvailable ? (
        <>
          <Typography.Text strong>{forecast.availableBikes} 台</Typography.Text>
          <br />
          <Typography.Text type="secondary">
            區間 {forecast.lowerBound}–{forecast.upperBound} 台
          </Typography.Text>
        </>
      ) : (
        <Typography.Text type="secondary">不可用：{forecast.reason}</Typography.Text>
      )}
    </div>
  );
}

export default function TemporalPanel() {
  const temporal = useTemporalPresentation();
  const latestPast = temporal.station?.past.at(-1) ?? null;

  return (
    <Card
      className="temporal-card"
      title="Past／Live／Predict"
      extra={<Tag color="gold">Frontend-local Mock</Tag>}
    >
      {temporal.error ? (
        <Alert
          type="error"
          showIcon
          message="Temporal Mock 載入失敗"
          description={temporal.error.message}
        />
      ) : temporal.station ? (
        <>
          <div className="temporal-toolbar">
            <Space wrap>
              <Select
                aria-label="選擇 Temporal Mock 站點"
                value={temporal.stationId}
                onChange={temporal.setStationId}
                options={temporal.stations.map((station) => ({
                  value: station.stationId,
                  label: station.stationName,
                }))}
              />
              <Tag>{temporal.timezone}</Tag>
            </Space>
            <Segmented
              value={temporal.mode}
              options={modeOptions}
              onChange={temporal.setMode}
            />
          </div>

          <div className="temporal-grid">
            <ObservationValue
              label="Past｜最近觀測"
              mode="past"
              selectedMode={temporal.mode}
              value={latestPast}
              note={`共 ${temporal.station.past.length} 筆本地觀測`}
            />
            <ObservationValue
              label="Live｜Mock 最新站況"
              mode="live"
              selectedMode={temporal.mode}
              value={temporal.station.live}
            />
            <section className={`temporal-value ${temporal.mode === "predict" ? "temporal-value-active" : ""}`}>
              <Tag color="purple">Predict｜固定展示</Tag>
              <div className="temporal-slots">
                {temporal.station.forecasts.map((forecast) => (
                  <ForecastValue key={forecast.offsetMinutes} forecast={forecast} />
                ))}
              </div>
            </section>
          </div>

          <Alert
            className="temporal-boundary-notice"
            type="info"
            showIcon
            message="固定 +30／+60 僅供前端展示，不是 Dispatch ETA，也不會送入派遣操作。"
          />
        </>
      ) : (
        <Empty description="沒有 frontend-local Temporal Mock" />
      )}
    </Card>
  );
}
