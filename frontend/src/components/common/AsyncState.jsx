import { Button, Empty, Result, Spin } from "antd";

export default function AsyncState({ loading, error, data, onRetry, children }) {
  if (loading) {
    return (
      <div className="center-state">
        <Spin size="large" tip="資料載入中…" />
      </div>
    );
  }

  if (error) {
    return (
      <Result
        status="error"
        title="資料載入失敗"
        subTitle={error.message || "資料格式不正確"}
        extra={<Button onClick={() => Promise.resolve(onRetry?.()).catch(() => {})}>重新載入</Button>}
      />
    );
  }

  if (!data) {
    return <Empty description="沒有可顯示的資料" />;
  }

  return children;
}
