"""戰情室顧問 3.21：Bedrock 成功、失敗降級、未登入擋下。"""
from __future__ import annotations

import pytest

from models_schema.assistant import TwinAssistantContext, TwinAssistantRequest, TwinDistrictHint


def _payload(**extra):
    body = {
        "question": extra.pop("question", None),
        "context": {
            "mode": "live",
            "n_stations": 12,
            "stations_source": "backend",
            "city_wide_ok": True,
            "headline": "全市空站率 50%。",
            "active_layers": ["gauge"],
            "layers": [
                {
                    "key": "gauge",
                    "title": "站點標記",
                    "data_mode": "real",
                    "metrics": [{"label": "空站率", "value": 50, "unit": "%"}],
                    "findings": ["全市 12 站中，空站 6（50%）。"],
                    "caveats": [],
                    "evidence": [{"label": "板橋區", "detail": "空站 6/6（100%）"}],
                }
            ],
            "top_districts": [{"district": "板橋區", "empty": 6, "count": 6, "empty_rate": 100}],
            "analysis_notes": [
                {"key": "gauge", "name": "站點標記", "info": "可借比例與狀態"}
            ],
        },
        "history": [],
    }
    body.update(extra)
    return body


def test_twin_assistant_requires_operator(client):
    r = client.post("/api/v1/assistant/twin", json=_payload(question="總結一下"))
    assert r.status_code == 401


def test_twin_assistant_uses_bedrock_when_available(client, monkeypatch):
    from core.assistant import service as svc

    monkeypatch.setattr(svc, "converse_text", lambda **kwargs: "Bedrock 摘要：空站率 50%。僅供參考，實際調度由規則引擎與人工決定。")
    r = client.post(
        "/api/v1/assistant/twin",
        json=_payload(question="總結一下"),
        headers={"X-Operator-Id": "OP-002"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "bedrock"
    assert body["advisory"] is True
    assert "50%" in body["text"]


def test_twin_assistant_falls_back_when_bedrock_fails(client, monkeypatch):
    from core.assistant import service as svc

    def _boom(**kwargs):
        raise RuntimeError("no_model_access")

    monkeypatch.setattr(svc, "converse_text", _boom)
    r = client.post(
        "/api/v1/assistant/twin",
        json=_payload(question="哪一區空站最集中？"),
        headers={"X-Operator-Id": "OP-002"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fallback"
    assert "板橋區" in body["text"]
    assert body["advisory"] is True


def test_twin_assistant_disabled_uses_fallback(client, monkeypatch):
    monkeypatch.setenv("BEDROCK_ENABLED", "false")
    r = client.post(
        "/api/v1/assistant/twin",
        json=_payload(),
        headers={"X-Operator-Id": "OP-001"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "fallback"
    assert "12 站" in body["text"]


def test_fallback_refuses_dispatch_and_unknown_numbers():
    from core.assistant.fallback import answer_twin_fallback

    ctx = TwinAssistantContext(
        mode="live",
        n_stations=3,
        city_wide_ok=True,
        top_districts=[TwinDistrictHint(district="新店區", empty=1, count=3, empty_rate=33.3)],
    )
    refuse = answer_twin_fallback(ctx, "直接派車去板橋車站補 20 台")
    assert "不能決定" in refuse or "規則引擎" in refuse
    unknown = answer_twin_fallback(ctx, "三重區今晚會不會下雨")
    assert "不可用" in unknown or "規則型降級" in unknown


def test_request_schema_caps_question():
    with pytest.raises(Exception):
        TwinAssistantRequest(question="x" * 501, context=TwinAssistantContext())


def test_history_starting_with_assistant_is_normalized():
    from core.assistant.twin_prompt import build_messages
    from models_schema.assistant import ChatTurn, TwinAssistantContext

    ctx = TwinAssistantContext(mode="live", n_stations=1, city_wide_ok=True)
    _, turns = build_messages(
        ctx,
        "白話說明一下",
        [ChatTurn(role="assistant", text="全市空站率 4.2%。")],
    )
    assert turns[0]["role"] == "user"
    assert [t["role"] for t in turns] == ["user"]
    roles = [t["role"] for t in turns]
    assert all(roles[i] != roles[i + 1] for i in range(len(roles) - 1))
