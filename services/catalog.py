from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from config import SUPPORTED_SPREADSHEET_EXTENSIONS


REQUIRED_COLUMNS = {
    "article": ("article", "артикул", "sku"),
    "name": ("name", "наименование", "название", "товар"),
}

OPTIONAL_COLUMNS = {
    "quantity": ("quantity", "qty", "количество", "шт", "остаток"),
    "supplier_site": ("supplier_site", "сайт", "домен", "supplier"),
    "supplier_article": ("supplier_article", "артикул поставщика", "supplier_sku"),
    "product_url": ("product_url", "url", "ссылка", "ссылка на товар"),
    "image_urls_raw": ("image_urls", "image_urls_raw", "картинки", "фото", "image_links"),
    "notes": ("notes", "комментарий", "notes"),
}


def normalize_headers(columns: list[str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    lowered = {column.strip().lower(): column for column in columns}
    for target, aliases in REQUIRED_COLUMNS.items():
        for alias in aliases:
            if alias in lowered:
                normalized[lowered[alias]] = target
                break
    for target, aliases in OPTIONAL_COLUMNS.items():
        for alias in aliases:
            if alias in lowered:
                normalized[lowered[alias]] = target
                break
    return normalized


def load_dataframe(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    extension = Path(file_name).suffix.lower()
    if extension not in SUPPORTED_SPREADSHEET_EXTENSIONS:
        raise ValueError(f"Неподдерживаемый формат файла: {extension}")

    if extension == ".csv":
        return pd.read_csv(BytesIO(file_bytes))
    return pd.read_excel(BytesIO(file_bytes))


def normalize_catalog_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    renamed = dataframe.rename(columns=normalize_headers(list(dataframe.columns)))
    missing = [column for column in REQUIRED_COLUMNS if column not in renamed.columns]
    if missing:
        raise ValueError(
            "Не найдены обязательные колонки: " + ", ".join(missing)
        )

    for column in OPTIONAL_COLUMNS:
        if column not in renamed.columns:
            renamed[column] = None

    prepared = renamed[
        [
            "article",
            "name",
            "quantity",
            "supplier_site",
            "supplier_article",
            "product_url",
            "image_urls_raw",
            "notes",
        ]
    ].copy()

    prepared["article"] = prepared["article"].astype(str).str.strip()
    prepared["name"] = prepared["name"].astype(str).str.strip()
    prepared["supplier_site"] = prepared["supplier_site"].fillna("").astype(str).str.strip()
    prepared["supplier_article"] = prepared["supplier_article"].fillna("").astype(str).str.strip()
    prepared["product_url"] = prepared["product_url"].fillna("").astype(str).str.strip()
    prepared["image_urls_raw"] = prepared["image_urls_raw"].fillna("").astype(str).str.strip()
    prepared["notes"] = prepared["notes"].fillna("").astype(str).str.strip()

    prepared = prepared[prepared["article"] != ""]
    prepared = prepared[prepared["name"] != ""]
    return prepared.reset_index(drop=True)
