import { parseAssistantBlocks, splitInlineMarks } from "../../utils/formatAssistantReply.js";

function InlineText({ text }) {
  return splitInlineMarks(text).map((part, index) =>
    part.bold ? <strong key={index}>{part.text}</strong> : <span key={index}>{part.text}</span>,
  );
}

export default function AssistantRichText({ text }) {
  const blocks = parseAssistantBlocks(text);
  if (!blocks.length) return null;
  return (
    <div className="assistant-rich">
      {blocks.map((block, index) => {
        if (block.type === "lead") {
          return (
            <p key={index} className="assistant-lead">
              <InlineText text={block.text} />
            </p>
          );
        }
        if (block.type === "heading") {
          return (
            <h3 key={index} className="assistant-heading">
              {block.text}
            </h3>
          );
        }
        if (block.type === "ul") {
          return (
            <ul key={index} className="assistant-list">
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>
                  <InlineText text={item} />
                </li>
              ))}
            </ul>
          );
        }
        return (
          <p key={index} className={block.type === "foot" ? "assistant-note" : undefined}>
            <InlineText text={block.text} />
          </p>
        );
      })}
    </div>
  );
}
