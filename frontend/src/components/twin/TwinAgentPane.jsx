import { MenuFoldOutlined, ToolOutlined } from "@ant-design/icons";
import { Button, Segmented } from "antd";
import { useEffect, useState } from "react";

const STORAGE_KEY = "youbike.twin.agentWidth";
const MIN_WIDTH = 320;
const MAX_WIDTH = 880;
const DEFAULT_WIDTH = 420;

const TAB_OPTIONS = [
  { value: "assistant", label: "研究助手" },
  { value: "optimization", label: "最適化審核" },
];

function clampWidth(value) {
  const max = Math.min(MAX_WIDTH, Math.round(window.innerWidth * 0.7));
  return Math.max(MIN_WIDTH, Math.min(max, Math.round(value)));
}

function readStoredWidth() {
  const saved = Number(globalThis.sessionStorage?.getItem(STORAGE_KEY));
  return Number.isFinite(saved) && saved >= MIN_WIDTH ? saved : DEFAULT_WIDTH;
}

export default function TwinAgentPane({
  open,
  onOpenChange,
  tab = "assistant",
  onTabChange,
  children,
}) {
  const [width, setWidth] = useState(readStoredWidth);

  useEffect(() => {
    globalThis.sessionStorage?.setItem(STORAGE_KEY, String(width));
  }, [width]);

  const onPointerDown = (event) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    document.body.classList.add("twin-agent-dragging");

    const onMove = (moveEvent) => {
      setWidth(clampWidth(startWidth + (startX - moveEvent.clientX)));
    };
    const onUp = () => {
      document.body.classList.remove("twin-agent-dragging");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  };

  return (
    <>
      <button
        type="button"
        className="twin-agent-rail"
        hidden={open}
        onClick={() => onOpenChange(true)}
      >
        <ToolOutlined />
        <span>戰情工具</span>
      </button>
      <aside
        className="twin-agent"
        style={{ width, display: open ? "flex" : "none" }}
        aria-label="戰情室右側工具"
        aria-hidden={!open}
      >
        <div
          className="twin-agent-handle"
          role="separator"
          aria-orientation="vertical"
          aria-label="調整右側欄寬度"
          onPointerDown={onPointerDown}
        />
        <div className="twin-agent-chrome">
          <Segmented size="small" value={tab} options={TAB_OPTIONS} onChange={onTabChange} />
          <Button
            type="text"
            size="small"
            icon={<MenuFoldOutlined />}
            onClick={() => onOpenChange(false)}
            aria-label="收合右側欄"
          />
        </div>
        <div className="twin-agent-slot">{children}</div>
      </aside>
    </>
  );
}
