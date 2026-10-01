from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    hf_token_configured: bool
    model: str
    fallback_models: list[str] = Field(default_factory=list)
    refine_enabled: bool = False


class ConfigResponse(BaseModel):
    max_upload_mb: int
    image_max_side: int
    accepted_types: list[str]
    requires_access_key: bool
    model: str


class SanitizeCounts(BaseModel):
    removed_scripts: int = 0
    removed_links: int = 0
    neutralized_css_urls: int = 0
    replaced_images: int = 0
    removed_embeds: int = 0
    removed_js_blocks: int = 0


class ImageInfo(BaseModel):
    width: int
    height: int
    orig_width: int
    orig_height: int


class UsageInfo(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None


class ResultPayload(BaseModel):
    html: str
    model: str
    finish_reason: Optional[str] = None
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)
    sanitize: SanitizeCounts
    palette: list[str] = Field(default_factory=list)
    image: ImageInfo
    usage: Optional[UsageInfo] = None
    elapsed_ms: int = 0


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool = False


class ErrorBody(BaseModel):
    detail: ErrorDetail


class StatusData(BaseModel):
    stage: Literal["preparing", "calling_model", "generating", "postprocessing"]
    note: Optional[str] = None
    model: Optional[str] = None


class DeltaData(BaseModel):
    text: str


def sse(event: str, data: dict | BaseModel) -> str:
    payload = data.model_dump_json(exclude_none=True) if isinstance(data, BaseModel) else _json(data)
    return f"event: {event}\ndata: {payload}\n\n"


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
