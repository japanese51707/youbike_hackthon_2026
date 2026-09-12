"""戰情室顧問端點（API 3.21，ADR-307）。"""

from fastapi import APIRouter, Depends, HTTPException

from auth import get_operator
from config_loader import get_config
from core.assistant import answer_twin
from core.assistant.bedrock import assistant_config
from core.assistant.service import AssistantRateLimited
from core.aws_local import load_local_aws_credentials
from models_schema.assistant import TwinAssistantRequest, TwinAssistantResponse

router = APIRouter(prefix="/api/v1", tags=["assistant"])


@router.get("/assistant/status")
def assistant_status():
    """戰情室顧問是否已讀到本機憑證。不回傳金鑰。"""
    loaded = load_local_aws_credentials()
    settings = assistant_config()
    return {
        "advisory": True,
        "provider": "bedrock",
        "enabled": settings["enabled"],
        "credentials_loaded": loaded["loaded"],
        "credentials_file": loaded["path"],
        "region": settings["region"],
        "model": settings["model_id"],
    }


@router.post("/assistant/twin", response_model=TwinAssistantResponse)
def twin_assistant(
    body: TwinAssistantRequest,
    operator: dict = Depends(get_operator),
):
    """摘要或追問當前戰情。只建議、不派工。"""
    limit = int((get_config().get("assistant") or {}).get("context_max_chars", 12000))
    if len(body.model_dump_json()) > limit + 2000:
        raise HTTPException(status_code=413, detail="戰情摘要過長，請只傳送當前洞察")
    try:
        return answer_twin(body, operator["operator_id"])
    except AssistantRateLimited:
        raise HTTPException(status_code=429, detail="顧問提問過於頻繁，請稍後再試")
