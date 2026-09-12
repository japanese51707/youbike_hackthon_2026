import { PhoneOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { Alert, Button, Input, Modal, Space, Typography, message } from "antd";
import { useState } from "react";
import { formatWaited, recordCaseAction } from "../../api/escalationApi.js";

/**
 * ADR-309 L2：等待跨過第二個門檻的強制彈窗。
 *
 * 刻意不能點外面關閉、不給右上角叉叉——三個出口都必須留下稽核軌跡。
 * ★三個出口都不關案：關案只認「有未結案任務涵蓋該站」或「站況恢復」。
 *   按鈕只會靜音一段時間，時鐘照走。
 */
export default function EscalationModal({ open, item, onDispatch, onDone }) {
  const [mode, setMode] = useState(null); // null | "call" | "defer"
  const [contact, setContact] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();

  if (!item) return null;
  const phone = item.contact?.電話 || item.contact?.phone || "";
  const contactName = item.contact?.姓名 || item.contact?.name || "值班窗口";

  const close = () => { setMode(null); setContact(""); setNote(""); };

  const submit = async (action, payload) => {
    setBusy(true);
    try {
      await recordCaseAction(item.case_id, action, payload);
      messageApi.success("已記錄，暫時靜音；仍未派工會再提示");
      close();
      onDone?.();
    } catch (err) {
      messageApi.error(err.message || "記錄失敗");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open={open}
      title={<span className="escalation-modal-title">緊急調度尚未處理</span>}
      closable={false}
      maskClosable={false}
      keyboard={false}
      footer={null}
      width={520}
    >
      {contextHolder}
      <Alert
        type="error"
        showIcon
        style={{ marginBottom: 14 }}
        title={`${item.station_name}　已等 ${formatWaited(item.waited_minutes)}`}
        description={`${item.district}｜${item.trigger_reason}${item.suggested_action ? `｜建議 ${item.suggested_action}` : ""}`}
      />
      <Typography.Paragraph type="secondary" className="escalation-modal-note">
        這張案件從 {item.opened_at?.replace("T", " ")} 開案到現在沒有派工。
        以下三個動作都會留下紀錄，<b>但都不會結案</b>——只有實際派工或站況恢復才會。
      </Typography.Paragraph>

      {mode === null ? (
        <Space orientation="vertical" style={{ width: "100%" }} size={10}>
          <Button type="primary" danger block size="large" icon={<ThunderboltOutlined />}
            onClick={() => { onDispatch?.(item); onDone?.(); }}>
            立即派工（帶我去組單）
          </Button>
          <Button block icon={<PhoneOutlined />} onClick={() => setMode("call")}>
            已電話聯絡 {phone ? `（${contactName} ${phone}）` : ""}
          </Button>
          <Button block type="text" onClick={() => setMode("defer")}>
            延後處理（需填原因）
          </Button>
        </Space>
      ) : null}

      {mode === "call" ? (
        <Space orientation="vertical" style={{ width: "100%" }} size={10}>
          {phone ? (
            <Typography.Paragraph>
              請致電 <b>{contactName}</b>：<a href={`tel:${phone}`}>{phone}</a>
            </Typography.Paragraph>
          ) : (
            <Alert type="warning" title="設定裡沒有這個行政區的值班聯絡方式" />
          )}
          <Input placeholder="實際聯絡對象（必填，例：值班 王小明 0912-000-000）"
            value={contact} onChange={(e) => setContact(e.target.value)} maxLength={120} />
          <Input.TextArea placeholder="備註（選填）" rows={2} value={note}
            onChange={(e) => setNote(e.target.value)} maxLength={500} />
          <Space>
            <Button type="primary" loading={busy} disabled={!contact.trim()}
              onClick={() => submit("called", { contact: contact.trim(), note: note.trim() })}>
              記錄已聯絡
            </Button>
            <Button onClick={close} disabled={busy}>返回</Button>
          </Space>
        </Space>
      ) : null}

      {mode === "defer" ? (
        <Space orientation="vertical" style={{ width: "100%" }} size={10}>
          <Input.TextArea placeholder="延後原因（必填，例：車隊全數出勤中，最快 20 分後有車）"
            rows={3} value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} />
          <Space>
            <Button type="primary" loading={busy} disabled={!note.trim()}
              onClick={() => submit("deferred", { note: note.trim() })}>
              記錄延後
            </Button>
            <Button onClick={close} disabled={busy}>返回</Button>
          </Space>
        </Space>
      ) : null}
    </Modal>
  );
}
