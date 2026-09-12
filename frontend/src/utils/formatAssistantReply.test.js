import test from "node:test";
import assert from "node:assert/strict";
import { parseAssistantBlocks, splitInlineMarks } from "./formatAssistantReply.js";

test("numbered bold headings become section titles", () => {
  const blocks = parseAssistantBlocks(
    "結論：全市空站率 5.1%。\n1. **站點標記（gauge）**：\n- 空站 82 站（5.1%）\n2. **壓力熱力圖（KDE）**：\n偏高站 788 座。\n僅供參考，實際調度由規則引擎與人工決定。",
  );
  assert.equal(blocks[0].type, "lead");
  assert.equal(blocks[1].type, "heading");
  assert.equal(blocks[1].text, "站點標記");
  assert.equal(blocks[2].type, "ul");
  assert.equal(blocks[2].items[0], "空站 82 站（5.1%）");
  assert.equal(blocks.at(-1).type, "foot");
});

test("inline bold marks stay as text parts", () => {
  const parts = splitInlineMarks("空站率 **5.1%** 偏高");
  assert.deepEqual(parts, [
    { bold: false, text: "空站率 " },
    { bold: true, text: "5.1%" },
    { bold: false, text: " 偏高" },
  ]);
});
