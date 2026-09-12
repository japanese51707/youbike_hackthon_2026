"""規則型戰情摘要：Bedrock 不可用時的確定性降級。數字只來自 context。"""

from __future__ import annotations

ADVISORY_NOTE = "（我僅提供理解與建議；是否調度由規則引擎與人工決定）"


def _metric_text(metric) -> str:
    unit = f" {metric.unit}" if metric.unit else ""
    if metric.value is None or metric.value == "":
        return f"{metric.label} 不可用"
    return f"{metric.label} {metric.value}{unit}"


def summarize_twin(context) -> str:
    """用洞察 context 組一段可核對的總結。"""
    mode_label = {"live": "即時", "past": "歷史", "predict": "預測"}.get(context.mode, context.mode)
    lines = [f"目前是{mode_label}戰情，來源 {context.stations_source or '不明'}，納入 {context.n_stations} 站。"]
    if context.observed_at:
        lines.append(f"觀測時間 {context.observed_at}。")
    if not context.city_wide_ok:
        lines.append(context.gate_reason or "全市結論已關閉，以下只複述已提供的圖層說明。")
    if context.headline:
        lines.append(context.headline)
    for layer in context.layers:
        bits = []
        if layer.findings:
            bits.append(layer.findings[0])
        elif layer.metrics:
            bits.append("、".join(_metric_text(m) for m in layer.metrics[:3]))
        if layer.caveats:
            bits.append(f"限制：{layer.caveats[0]}")
        if bits:
            lines.append(f"{layer.title}：{' '.join(bits)}")
    if context.top_districts:
        hot = context.top_districts[0]
        lines.append(
            f"空站較集中：{hot.district}（{hot.empty}/{hot.count}，{hot.empty_rate}%）。"
        )
    lines.append(ADVISORY_NOTE)
    return "\n".join(lines)


def answer_twin_fallback(context, question: str | None) -> str:
    """範圍內用 context 回答；問不到就導回可問的項目。"""
    q = (question or "").strip()
    if not q:
        return summarize_twin(context)

    if any(key in q for key in ("總結", "摘要", "現況", "情況", "怎麼了")):
        return summarize_twin(context)

    if any(key in q for key in ("空站", "哪一區", "哪區", "熱點", "集中")):
        if context.top_districts:
            hot = context.top_districts[0]
            extra = "、".join(
                f"{row.district} {row.empty_rate}%" for row in context.top_districts[:3]
            )
            return f"依目前洞察，空站較集中在 {hot.district}（{hot.empty}/{hot.count}，{hot.empty_rate}%）。前幾區：{extra}。{ADVISORY_NOTE}"
        gauge = next((layer for layer in context.layers if layer.key == "gauge"), None)
        if gauge and gauge.findings:
            return f"{gauge.findings[0]} {ADVISORY_NOTE}"
        return f"目前 context 沒有行政區空站排名，無法判斷哪一區最集中。{ADVISORY_NOTE}"

    if any(key in q for key in ("滿站",)):
        if context.top_full:
            names = "、".join(s.station_name for s in context.top_full[:5])
            return f"目前列出的滿站樣本：{names}。完整數字以右側解讀為準。{ADVISORY_NOTE}"
        return f"目前 context 沒有滿站名單。{ADVISORY_NOTE}"

    if any(key in q for key in ("什麼意思", "是什麼", "怎麼算", "方法", "Gi", "KDE", "Voronoi", "覆蓋", "集水")):
        notes = context.analysis_notes or []
        if notes:
            parts = [f"{note.name}：{note.info}" for note in notes]
            return "這頁分析方法如下。沒有出現在目前圖層／context 的資料我不會編造。\n" + "\n".join(parts)
        return "目前沒有帶分析方法說明。可先勾選左側圖層，再問一次。"

    if any(key in q for key in ("派工", "派遣", "派車", "派哪", "去哪站", "哪台車")):
        return f"我不能決定或執行調度。派哪台車、去哪一站由規則引擎與人工閘門決定。{ADVISORY_NOTE}"

    matched = [layer for layer in context.layers if layer.title in q or layer.key in q]
    if matched:
        layer = matched[0]
        finding = layer.findings[0] if layer.findings else "此層目前沒有結論。"
        caveat = layer.caveats[0] if layer.caveats else ""
        return f"{layer.title}：{finding} {caveat} {ADVISORY_NOTE}".strip()

    if context.headline:
        return f"我只能根據目前戰情數字回答。當前摘要：{context.headline} {ADVISORY_NOTE}"
    return (
        "我是戰情室顧問（規則型降級）。可問：現況總結、空站／哪一區、滿站、"
        "圖層方法是什麼意思。沒出現在目前洞察裡的數字會回「不可用」。"
    )
