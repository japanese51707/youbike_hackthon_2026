import { useEffect, useState } from "react";

// 真機窄螢幕（含手機預覽以外的實機）。桌機預覽仍用外框，不靠這個判斷。
export default function useNarrowPhone(maxWidthPx = 520) {
  const query = `(max-width: ${maxWidthPx}px)`;
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );

  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = () => setNarrow(media.matches);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [query]);

  return narrow;
}
