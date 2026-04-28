from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
MEDIA_DIR = BASE_DIR / "media"
EXPORTS_DIR = BASE_DIR / "exports"
TEMPLATES_DIR = BASE_DIR / "templates"
DB_PATH = DATA_DIR / "updatpic.db"
CLIENT_PROFILES_PATH = DATA_DIR / "client_profiles.json"
AI_SETTINGS_PATH = DATA_DIR / "ai_settings.json"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/135.0.0.0 Safari/537.36"
)

SUPPORTED_SPREADSHEET_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def ensure_directories() -> None:
    for path in (DATA_DIR, MEDIA_DIR, EXPORTS_DIR, TEMPLATES_DIR):
        path.mkdir(parents=True, exist_ok=True)
