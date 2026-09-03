import { Button, Empty, Result, Spin } from "antd";

export default function AsyncState({ loading, error, data, onRetry, children }) {
  if (loading) {
    return (
      <div className="center-state">
        <Spin size="large" tip="載入 Mock 資料中…" />
      </div>
    );
  }

  if (error) {
    return (
      <Result
        status="error"
        title="資料載入失敗"
        subTitle={error.message || "Mock 資料格式不正確"}
        extra={<Button onClick={onRetry}>重新載入</Button>}
      />
    );
  }

  if (!data) {
    return <Empty description="沒有可顯示的資料" />;
  }

  return children;
}
