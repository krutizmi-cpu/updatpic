from __future__ import annotations

from io import BytesIO
from typing import Any

import pandas as pd

from services.image_search import (
    is_probable_image_url,
    is_yandex_disk_public_url,
    split_reference_urls,
)


LINK_EXPORT_ALIASES = {
    "article": ("article", "артикул", "sku"),
    "client_code": (
        "client_code",
        "client code",
        "код клиента",
        "код цветомодели",
        "код цветовой модели",
        "цветомодель",
        "штрихкод",
        "штрих-код",
        "штрихкод товара",
        "штрих-код товара",
        "barcode",
    ),
    "image_urls_raw": (
        "image_urls_raw",
        "image_urls",
        "photo_urls",
        "photo links",
        "ссылки на фото",
        "ссылка на фото",
        "ссылки",
        "фото",
        "ссылки фото",
        "url фото",
    ),
}


def normalize_link_export_headers(columns: list[str]) -> dict[str, str]:
    lowered = {
        str(column).strip().lower().replace("\n", " ").replace("\r", " "): column
        for column in columns
    }
    renamed: dict[str, str] = {}
    for target, aliases in LINK_EXPORT_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                renamed[lowered[alias]] = target
                break
    return renamed


def normalize_link_export_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    renamed = dataframe.rename(columns=normalize_link_export_headers(list(dataframe.columns)))
    for required in ("client_code", "image_urls_raw"):
        if required not in renamed.columns:
            raise ValueError(
                f"Не найдена колонка {required}. "
                "Ожидаются код клиента и колонка со ссылками на фото."
            )

    if "article" not in renamed.columns:
        renamed["article"] = ""

    prepared = renamed[["article", "client_code", "image_urls_raw"]].copy()
    for column in ("article", "client_code", "image_urls_raw"):
        prepared[column] = prepared[column].fillna("").astype(str).str.strip()
    prepared = prepared[
        (prepared["client_code"] != "") & (prepared["image_urls_raw"] != "")
    ]
    return prepared.reset_index(drop=True)


def build_marketplace_link_export(
    client_key: str,
    mapping_df: pd.DataFrame,
) -> tuple[bytes, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for _, row in mapping_df.iterrows():
        article = row.get("article", "")
        client_code = row["client_code"]
        raw_urls = row["image_urls_raw"]
        normalized_links, warnings = normalize_marketplace_links(client_key, raw_urls)
        rows.append(
            {
                "article": article,
                "client_code": client_code,
                "normalized_links": format_links_for_client(client_key, normalized_links),
                "status": "ok" if normalized_links else "warning",
                "message": "; ".join(warnings) if warnings else "OK",
                "link_count": len(normalized_links),
            }
        )

    report_df = pd.DataFrame(rows)
    upload_df = build_upload_dataframe(client_key, report_df)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        upload_df.to_excel(writer, index=False, sheet_name="Загрузка")
        report_df.to_excel(writer, index=False, sheet_name="Отчёт")

        upload_sheet = writer.sheets["Загрузка"]
        report_sheet = writer.sheets["Отчёт"]
        for worksheet in (upload_sheet, report_sheet):
            worksheet.freeze_panes = "A2"

        set_widths(upload_sheet, [22, 90])
        set_widths(report_sheet, [18, 22, 90, 12, 50, 12])

    return output.getvalue(), report_df


def build_upload_dataframe(client_key: str, report_df: pd.DataFrame) -> pd.DataFrame:
    if client_key == "sportmaster":
        return pd.DataFrame(
            {
                "Код цветомодели": report_df["client_code"],
                "Ссылки на фото": report_df["normalized_links"],
            }
        )
    if client_key == "detmir":
        return pd.DataFrame(
            {
                "Штрихкод товара": report_df["client_code"],
                "Ссылки на фото": report_df["normalized_links"],
            }
        )
    return pd.DataFrame(
        {
            "Код клиента": report_df["client_code"],
            "Ссылки на фото": report_df["normalized_links"],
        }
    )


def normalize_marketplace_links(client_key: str, raw_urls: str) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    links = split_reference_urls(raw_urls)
    valid_links: list[str] = []

    if client_key == "sportmaster":
        for link in links:
            if is_yandex_disk_public_url(link):
                warnings.append("Яндекс Диск не подходит для Спортмастера: ссылка не содержит расширение файла.")
                continue
            if not is_probable_image_url(link):
                warnings.append("Для Спортмастера нужны прямые ссылки на jpg/jpeg/png.")
                continue
            valid_links.append(link)
        return valid_links, dedupe_messages(warnings)

    if client_key == "detmir":
        for link in links:
            if is_probable_image_url(link) or is_yandex_disk_public_url(link):
                valid_links.append(link)
            else:
                warnings.append("Для Детского Мира нужны прямые ссылки на изображение или публичные ссылки Яндекс Диска.")
        if len(valid_links) > 30:
            warnings.append("Оставлены только первые 30 ссылок по лимиту Детского Мира.")
            valid_links = valid_links[:30]
        return valid_links, dedupe_messages(warnings)

    return links, warnings


def format_links_for_client(client_key: str, links: list[str]) -> str:
    if client_key == "sportmaster":
        return ";".join(links)
    if client_key == "detmir":
        return "\n".join(links)
    return "\n".join(links)


def dedupe_messages(messages: list[str]) -> list[str]:
    return list(dict.fromkeys(messages))


def set_widths(worksheet: Any, widths: list[int]) -> None:
    for index, width in enumerate(widths, start=1):
        column_letter = chr(64 + index)
        worksheet.column_dimensions[column_letter].width = width
