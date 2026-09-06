import { Card, Statistic, Typography } from "antd";

export default function MetricCard({ title, value, suffix, precision, note, tone }) {
  return (
    <Card className={`metric-card ${tone ? `metric-${tone}` : ""}`}>
      <Statistic title={title} value={value} suffix={suffix} precision={precision} />
      {note ? <Typography.Text type="secondary">{note}</Typography.Text> : null}
    </Card>
  );
}
