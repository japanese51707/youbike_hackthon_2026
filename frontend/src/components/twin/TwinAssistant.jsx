import { SendOutlined } from "@ant-design/icons";
import { Button, Input, Tag } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import { getActorId, isApiMode, request } from "../../api/httpClient.js";
import { compactTwinContext, fallbackTwinAnswer } from "../../utils/twinAssistantContext.js";
import AssistantRichText from "./AssistantRichText.jsx";

const SUGGESTIONS = [
  "快速總結當前情況",
  "哪一區空站最集中？",
  "這層 Gi* 是什麼意思？",
  "覆蓋缺口代表什麼？",
];

export default function TwinAssistant({
  report,
  snapshot = [],
  visibleLayers = [],
  dataReady = false,
}) {
  const context = useMemo(
    () => compactTwinContext(report, { snapshot, visibleLayers }),
    [report, snapshot, visibleLayers],
  );
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState("fallback");
  const [ready, setReady] = useState(null);
  const bodyRef = useRef(null);
  const askedRef = useRef(false);

  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages, busy]);

  useEffect(() => {
    if (!isApiMode) return undefined;
    let activeRequest = true;
    request("/assistant/status")
      .then((payload) => {
        if (activeRequest) setReady(payload);
      })
      .catch(() => {
        if (activeRequest) setReady({ credentials_loaded: false });
      });
    return () => {
      activeRequest = false;
    };
  }, []);

  const ask = async (text) => {
    if (!dataReady || busy) return;
    const question = (text ?? input).trim();
    const history = messages.slice(-8).map((m) => ({ role: m.role, text: m.text }));
    setBusy(true);
    setMessages((prev) => (question ? [...prev, { role: "user", text: question }] : prev));
    setInput("");
    try {
      const canCall = isApiMode && getActorId();
      if (!canCall) {
        const reply = fallbackTwinAnswer(context, question);
        setSource("fallback");
        setMessages((prev) => [...prev, { role: "assistant", text: reply }]);
        return;
      }
      const payload = await request("/assistant/twin", {
        method: "POST",
        body: { question: question || null, context, history },
        timeoutMs: 35000,
      });
      setSource(payload.source || "bedrock");
      setMessages((prev) => [...prev, { role: "assistant", text: payload.text }]);
    } catch (error) {
      const reply = fallbackTwinAnswer(context, question);
      setSource("fallback");
      setMessages((prev) => [
        ...prev,
        { role: "assistant", text: `${reply}\n（遠端顧問暫時不可用：${error.message}）` },
      ]);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (askedRef.current || !dataReady || !report) return undefined;
    askedRef.current = true;
    ask("");
    return undefined;
    // 等地圖站況就緒後只自動總結一次；之後改圖層由使用者再問。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataReady, report]);

  return (
    <div className="assistant twin-agent-chat">
        <div className="assistant-head">
          <span className="assistant-title">當前解讀顧問</span>
          <Tag color={source === "bedrock" ? "green" : "gold"}>
            {source === "bedrock" ? "AI 生成" : "規則型降級"}
          </Tag>
        </div>

        <div className="assistant-body" ref={bodyRef}>
          {!dataReady && !messages.length ? (
            <div className="assistant-note">地圖站況載入中，就緒後再自動總結。</div>
          ) : null}
          {messages.map((m, i) => (
            <div key={`${m.role}-${i}`} className={`assistant-msg assistant-${m.role}`}>
              {m.role === "assistant" ? (
                <AssistantRichText text={m.text} />
              ) : (
                m.text
              )}
            </div>
          ))}
          {busy ? <div className="assistant-msg assistant-assistant">整理當前戰情…</div> : null}
        </div>

        <div className="assistant-suggestions">
          {SUGGESTIONS.map((s) => (
            <Tag key={s} className="assistant-chip" onClick={() => dataReady && !busy && ask(s)}>
              {s}
            </Tag>
          ))}
        </div>

        <div className="assistant-input">
          <Input
            value={input}
            placeholder={dataReady ? "問當前地圖與洞察，例如：哪一區最空？" : "地圖資料載入後即可詢問"}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={() => dataReady && !busy && ask()}
            disabled={!dataReady || busy}
            allowClear
          />
          <Button type="primary" icon={<SendOutlined />} onClick={() => ask()} loading={busy} disabled={!dataReady} />
        </div>

        <div className="assistant-foot">
          AI 生成僅供參考。數字以地圖解讀與系統事實為準；我不會派工。缺資料就說不可用。
          {!isApiMode || !getActorId()
            ? " 目前用規則型降級（Mock 或尚未選擇操作身分）。"
            : ready?.credentials_loaded
              ? ` 已讀到本機 AWS 憑證（${ready.region}／${ready.model}）。`
              : " 尚未讀到 secrets/aws-credentials，會先用規則型降級。"}
        </div>
    </div>
  );
}
