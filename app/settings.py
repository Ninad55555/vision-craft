from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    hf_token: str = ""
    hf_base_url: str = "https://router.huggingface.co/v1"
    hf_model_id: str = "Qwen/Qwen3-VL-235B-A22B-Instruct"
    hf_fallback_model_ids: str = ""
    max_output_tokens: int = 8192
    temperature: float = 0.2
    request_timeout_seconds: float = 300
    max_retries: int = 2

    image_max_side: int = 1600
    max_upload_mb: int = 10
    max_image_payload_kb: int = 3000

    app_host: str = "127.0.0.1"
    app_port: int = 8000
    cors_origins: str = "http://127.0.0.1:8000,http://localhost:8000"
    app_access_key: str = ""
    rate_limit_per_minute: int = 6
    log_level: str = "INFO"
    trust_proxy: bool = False

    enable_refine_loop: bool = False
    refine_max_iterations: int = 2

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.hf_fallback_model_ids.split(",") if m.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
