import { DownOutlined, RobotOutlined, SendOutlined } from "@ant-design/icons";
import { Button, Input, Tag } from "antd";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  answerOverview,
  summarizeOverview,
} from "../../utils/overviewAssistant.js";

// AI 營運助理（Demo 規則型，非真實 LLM）：進場自動摘要，可問問題。
// 全部答案來自既有營運資料；無外部服務、無金鑰、不進 payload。
const SUGGESTIONS = [
  "現在該優先處理什麼？",
  "哪一區最需關注？",
  "服務水準達標嗎？",
  "改善成效如何？",
];

export default function OverviewAssistant({ data }) {
  const summary = useMemo(() => summarizeOverview(data), [data]);
  const [messages, setMessages] = useState(() => [
    { role: "assistant", text: `目前營運摘要：\n・${summary.join("\n・")}` },
  ]);
  const [input, setInput] = useState("");
  const [open, setOpen] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    if (open && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages, open]);

  if (!open) {
    return (
      <button type="button" className="assistant-fab" onClick={() => setOpen(true)}>
        <RobotOutlined /> AI 助理
      </button>
    );
  }

  const send = (text) => {
    const question = (text ?? input).trim();
    if (!question) return;
    const reply = answerOverview(data, question);
    setMessages((prev) => [
      ...prev,
      { role: "user", text: question },
      { role: "assistant", text: reply },
    ]);
    setInput("");
  };

  return (
    <div className="assistant-float">
      <div className="assistant">
        <div className="assistant-head">
          <span className="assistant-title">
            <RobotOutlined /> AI 營運助理
          </span>
          <span className="assistant-head-right">
            <Tag color="gold">Demo 規則型</Tag>
            <Button
              type="text"
              size="small"
              icon={<DownOutlined />}
              onClick={() => setOpen(false)}
              aria-label="收起 AI 助理"
            />
          </span>
        </div>

      <div className="assistant-body" ref={bodyRef}>
        {messages.map((m, i) => (
          <div key={i} className={`assistant-msg assistant-${m.role}`}>
            {m.text.split("\n").map((line, j) => (
              <div key={j}>{line}</div>
            ))}
          </div>
        ))}
      </div>

      <div className="assistant-suggestions">
        {SUGGESTIONS.map((s) => (
          <Tag key={s} className="assistant-chip" onClick={() => send(s)}>
            {s}
          </Tag>
        ))}
      </div>

      <div className="assistant-input">
        <Input
          value={input}
          placeholder="問營運數據，例如：哪一區最需關注？"
          onChange={(e) => setInput(e.target.value)}
          onPressEnter={() => send()}
          allowClear
        />
        <Button type="primary" icon={<SendOutlined />} onClick={() => send()} />
      </div>

        <div className="assistant-foot">
          決策支援顧問（Demo 規則型，非真實 LLM）：僅提供理解與建議，實際調度由規則引擎與人工決定。是否接 LLM 見 ADR-301（待後端決定）。
        </div>
      </div>
    </div>
  );
}
