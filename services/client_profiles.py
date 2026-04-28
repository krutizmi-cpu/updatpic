from __future__ import annotations

import json
from copy import deepcopy

from config import CLIENT_PROFILES_PATH, ensure_directories


DEFAULT_CLIENT_PROFILES = {
    "sportmaster": {
        "label": "Спортмастер",
        "file_name_template": "{client_code}_{index}",
        "allowed_extensions": ["jpg", "jpeg", "png"],
        "max_file_size_mb": 50,
        "index_padding": 1,
        "requires_client_code": True,
        "client_code_label": "Код цветомодели",
        "notes": [
            "Фото должны соответствовать требованиям модерации Спортмастера.",
            "Для прямых ссылок используйте отдельную ссылку на каждое фото через ; без пробелов.",
            "Ссылка должна быть открытой и заканчиваться на jpg, jpeg или png.",
            "На фото не должно быть ссылок, водяных знаков и постороннего ассортимента.",
        ],
        "source_reference": "https://seller-help.sportmaster.ru/pages/viewpage.action?pageId=48365664",
    },
    "detmir": {
        "label": "Детский Мир",
        "file_name_template": "{client_code}_{index}",
        "allowed_extensions": ["jpg", "jpeg", "png", "webp"],
        "max_file_size_mb": 1,
        "min_long_side_px": 1000,
        "max_long_side_px": 8000,
        "max_images": 30,
        "index_padding": 2,
        "requires_client_code": True,
        "client_code_label": "Штрихкод товара",
        "notes": [
            "Для массовой загрузки имя файла должно быть в формате штрихкод_номер-фото.",
            "Поддерживаются jpg, png и webp; размер файла должен быть до 1 МБ.",
            "Порядок фото задаётся именем файла, прямые ссылки можно давать списком.",
        ],
        "source_reference": "https://help.detmir.market/edit-media",
    },
}


def ensure_client_profiles() -> None:
    ensure_directories()
    if CLIENT_PROFILES_PATH.exists():
        return
    CLIENT_PROFILES_PATH.write_text(
        json.dumps(DEFAULT_CLIENT_PROFILES, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_client_profiles() -> dict[str, dict]:
    ensure_client_profiles()
    return json.loads(CLIENT_PROFILES_PATH.read_text(encoding="utf-8"))


def get_client_profile(client_key: str) -> dict:
    profiles = load_client_profiles()
    if client_key not in profiles:
        raise KeyError(f"Неизвестный клиент: {client_key}")
    return deepcopy(profiles[client_key])
