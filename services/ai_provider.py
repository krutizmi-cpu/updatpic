from __future__ import annotations

import json
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from openai import OpenAI

from config import AI_SETTINGS_PATH, ensure_directories


DEFAULT_AI_SETTINGS = {
    "provider_label": "NVIDIA NIM",
    "base_url": "https://integrate.api.nvidia.com/v1",
    "model": "deepseek-ai/deepseek-v3.2",
    "api_key": "",
    "temperature": 0.2,
    "top_p": 0.95,
    "max_tokens": 128,
    "last_check_ok": None,
    "last_check_message": "Проверка ещё не запускалась.",
    "last_check_at": "",
}

MODEL_PRESETS = [
    "deepseek-ai/deepseek-v3.2",
    "deepseek-ai/deepseek-v3.1-terminus",
    "deepseek-ai/deepseek-r1",
    "nvidia/llama-3.3-nemotron-super-49b-v1.5",
]


@dataclass
class ProviderCheckResult:
    ok: bool
    message: str
    checked_at: str


def ensure_ai_settings() -> None:
    ensure_directories()
    if AI_SETTINGS_PATH.exists():
        return
    AI_SETTINGS_PATH.write_text(
        json.dumps(DEFAULT_AI_SETTINGS, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_ai_settings() -> dict[str, Any]:
    ensure_ai_settings()
    file_settings = json.loads(AI_SETTINGS_PATH.read_text(encoding="utf-8"))
    settings = deepcopy(DEFAULT_AI_SETTINGS)
    settings.update(file_settings)

    env_overrides = {
        "base_url": os.getenv("UPDATPIC_LLM_BASE_URL", "").strip(),
        "model": os.getenv("UPDATPIC_LLM_MODEL", "").strip(),
        "api_key": (
            os.getenv("UPDATPIC_LLM_API_KEY", "").strip()
            or os.getenv("NVIDIA_API_KEY", "").strip()
            or os.getenv("NVIDIA_NIM_API_KEY", "").strip()
        ),
    }
    for key, value in env_overrides.items():
        if value:
            settings[key] = value
    return settings


def save_ai_settings(settings: dict[str, Any]) -> None:
    ensure_directories()
    current = deepcopy(DEFAULT_AI_SETTINGS)
    current.update(settings)
    AI_SETTINGS_PATH.write_text(
        json.dumps(current, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update_ai_settings(
    *,
    base_url: str,
    model: str,
    api_key: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> dict[str, Any]:
    settings = load_ai_settings()
    settings.update(
        {
            "base_url": base_url.strip(),
            "model": model.strip(),
            "api_key": api_key.strip(),
            "temperature": float(temperature),
            "top_p": float(top_p),
            "max_tokens": int(max_tokens),
        }
    )
    save_ai_settings(settings)
    return settings


def build_openai_client(settings: dict[str, Any] | None = None) -> OpenAI:
    resolved = settings or load_ai_settings()
    return OpenAI(
        base_url=str(resolved["base_url"]).rstrip("/"),
        api_key=str(resolved["api_key"]),
    )


def check_provider_connection(settings: dict[str, Any] | None = None) -> ProviderCheckResult:
    resolved = settings or load_ai_settings()
    checked_at = now_iso()

    if not str(resolved.get("api_key", "")).strip():
        result = ProviderCheckResult(
            ok=False,
            message="API key не задан. Введите его в настройках AI.",
            checked_at=checked_at,
        )
        persist_check_result(resolved, result)
        return result

    try:
        client = build_openai_client(resolved)
        response = client.chat.completions.create(
            model=str(resolved["model"]),
            messages=[{"role": "user", "content": "Reply with OK"}],
            temperature=0,
            top_p=1,
            max_tokens=min(int(resolved.get("max_tokens", 128)), 16),
            stream=False,
        )
        content = ""
        if response.choices:
            content = (response.choices[0].message.content or "").strip()
        result = ProviderCheckResult(
            ok=True,
            message=f"Подключение работает. Ответ модели: {content or 'OK'}",
            checked_at=checked_at,
        )
    except Exception as exc:
        result = ProviderCheckResult(
            ok=False,
            message=normalize_provider_error(exc),
            checked_at=checked_at,
        )

    persist_check_result(resolved, result)
    return result


def persist_check_result(settings: dict[str, Any], result: ProviderCheckResult) -> None:
    updated = deepcopy(settings)
    updated["last_check_ok"] = result.ok
    updated["last_check_message"] = result.message
    updated["last_check_at"] = result.checked_at
    save_ai_settings(updated)


def mask_api_key(api_key: str) -> str:
    if not api_key:
        return "не задан"
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:6]}...{api_key[-4:]}"


def current_status_label(settings: dict[str, Any]) -> tuple[str, str]:
    ok = settings.get("last_check_ok")
    if ok is True:
        return "success", "Ключ работает"
    if ok is False:
        return "error", "Ключ или модель не работают"
    return "warning", "Проверка не запускалась"


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def normalize_provider_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    lowered = message.lower()
    if "401" in lowered or "authentication" in lowered or "invalid api key" in lowered:
        return "Ключ не прошёл авторизацию. Проверьте API key или выпустите новый."
    if "403" in lowered:
        return "Доступ запрещён для этой модели или ключа."
    if "404" in lowered:
        return "Модель или base URL не найдены."
    if "429" in lowered:
        return "Лимит запросов исчерпан или free endpoint временно перегружен."
    if "connection" in lowered or "timeout" in lowered:
        return "Нет соединения с AI-провайдером или запрос истёк по таймауту."
    return f"Проверка не прошла: {message}"
