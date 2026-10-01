from __future__ import annotations

from app.settings import Settings


def test_env_file_is_loaded(tmp_path):
    env = tmp_path / ".env"
    env.write_text("HF_MODEL_ID=env-file-model\nMAX_OUTPUT_TOKENS=1234\nNOT_A_SETTING=ignored\n")
    s = Settings(_env_file=env)
    assert s.hf_model_id == "env-file-model"
    assert s.max_output_tokens == 1234


def test_fallback_models_parsed():
    s = Settings(hf_fallback_model_ids="a, b,,c ")
    assert s.fallback_models == ["a", "b", "c"]


def test_startup_tolerates_missing_token():
    s = Settings(hf_token="")
    assert s.hf_token == ""
