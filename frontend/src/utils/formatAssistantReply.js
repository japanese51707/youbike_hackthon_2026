// 把顧問回覆收成可排版的區塊。只認標題／條列／粗體，不當 HTML 渲染。

function stripWrap(text) {
  return String(text || "")
    .replace(/^\*\*(.+)\*\*$/s, "$1")
    .replace(/^`(.+)`$/, "$1")
    .trim();
}

export function splitInlineMarks(text) {
  return String(text || "")
    .split(/(\*\*[^*]+\*\*)/g)
    .filter((part) => part !== "")
    .map((part) => {
      const bold = part.match(/^\*\*(.+)\*\*$/);
      return bold ? { bold: true, text: bold[1] } : { bold: false, text: part };
    });
}

export function parseAssistantBlocks(text) {
  const lines = String(text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks = [];
  let list = null;

  const flushList = () => {
    if (list) {
      blocks.push(list);
      list = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) {
      flushList();
      continue;
    }

    const headingMd = line.match(/^#{1,3}\s+(.+)/);
    if (headingMd) {
      flushList();
      blocks.push({ type: "heading", text: stripWrap(headingMd[1]) });
      continue;
    }

    const numberedTitle = line.match(/^\d+[\.、)]\s+\*\*(.+?)\*\*\s*[:：]?\s*(.*)$/);
    if (numberedTitle) {
      flushList();
      blocks.push({ type: "heading", text: numberedTitle[1].replace(/（.*?）/g, "").trim() });
      if (numberedTitle[2]) blocks.push({ type: "p", text: numberedTitle[2] });
      continue;
    }

    if (/^結論[:：]/.test(line) || /^\*\*結論/.test(line)) {
      flushList();
      blocks.push({ type: "lead", text: stripWrap(line.replace(/^\*\*|\*\*$/g, "")) });
      continue;
    }

    const bullet = line.match(/^[-*•]\s+(.+)/);
    if (bullet) {
      if (!list) list = { type: "ul", items: [] };
      list.items.push(stripWrap(bullet[1]));
      continue;
    }

    flushList();
    blocks.push({ type: line.startsWith("僅供參考") ? "foot" : "p", text: stripWrap(line) });
  }
  flushList();
  return blocks;
}
