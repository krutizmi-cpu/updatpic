from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd
from PIL import Image
import requests

from db import fetch_product_by_article, fetch_product_images
from services.client_profiles import get_client_profile
from services.image_search import (
    infer_extension,
    parse_direct_image_urls,
    request_headers,
    resolve_download_url,
    split_reference_urls,
)


CLIENT_MAPPING_ALIASES = {
    "article": ("article", "артикул", "артикул товара", "sku"),
    "client_code": (
        "client_code",
        "client code",
        "код клиента",
        "код цветомодели*",
        "код цветомодели",
        "код цветомодели ",
        "код цветовой модели",
        "код модели цвета",
        "цветомодель",
        "штрихкод",
        "штрих-код",
        "штрихкод товара",
        "штрих-код товара",
        "barcode",
        "штрихкод*",
        "штрихкод товара*",
    ),
}

CLIENT_UPLOAD_ALIASES = {
    **CLIENT_MAPPING_ALIASES,
    "source_mode": (
        "source_mode",
        "photo_source",
        "источник фото",
        "режим",
        "тип выгрузки",
        "тип источника",
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
        "ссылки на изображения товара",
        "ссылки на изображения",
    ),
}

CATALOG_SOURCE_ALIASES = {
    "catalog",
    "local",
    "local_catalog",
    "from_catalog",
    "из каталога",
    "каталог",
    "локально",
    "локальный каталог",
    "спарсено",
    "спарсила система",
}

LINK_SOURCE_ALIASES = {
    "links",
    "ready_links",
    "from_links",
    "url",
    "urls",
    "готовые ссылки",
    "ссылки",
    "из ссылок",
    "внешние ссылки",
}

SPORTMASTER_CODE_PATTERN = re.compile(r"^[A-Z0-9 .#_+\-]+$")
DETMIR_CODE_PATTERN = re.compile(r"^[0-9, ]+$")


@dataclass
class ExportRowResult:
    article: str
    client_code: str
    status: str
    message: str
    exported_files: int


@dataclass
class ClientExportArtifacts:
    catalog_zip_bytes: bytes | None
    catalog_report_rows: list[ExportRowResult]
    catalog_rows_count: int


def normalize_mapping_headers(columns: list[str]) -> dict[str, str]:
    lowered = {
        str(column).strip().lower().replace("\n", " ").replace("\r", " "): column
        for column in columns
    }
    renamed: dict[str, str] = {}
    for target, aliases in CLIENT_MAPPING_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                renamed[lowered[alias]] = target
                break
    return renamed


def normalize_mapping_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    renamed = dataframe.rename(columns=normalize_mapping_headers(list(dataframe.columns)))
    for required in ("article", "client_code"):
        if required not in renamed.columns:
            raise ValueError(
                f"Не найдена колонка {required}. Ожидаются заголовки `article` и `client_code` "
                "или их русские аналоги."
            )
    prepared = renamed[["article", "client_code"]].copy()
    prepared["article"] = prepared["article"].astype(str).str.strip()
    prepared["client_code"] = prepared["client_code"].astype(str).str.strip()
    prepared = prepared[(prepared["article"] != "") & (prepared["client_code"] != "")]
    return prepared.reset_index(drop=True)


def normalize_client_upload_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    lowered = {
        str(column).strip().lower().replace("\n", " ").replace("\r", " "): column
        for column in dataframe.columns
    }
    renamed = dataframe.rename(
        columns={
            original: target
            for target, aliases in CLIENT_UPLOAD_ALIASES.items()
            for alias in aliases
            for normalized, original in lowered.items()
            if alias == normalized
        }
    )

    if "client_code" not in renamed.columns:
        raise ValueError(
            "Не найдена колонка client_code. Ожидается код цветомодели или штрихкод товара."
        )

    for optional_column in ("article", "source_mode", "image_urls_raw"):
        if optional_column not in renamed.columns:
            renamed[optional_column] = ""

    prepared = renamed[["article", "client_code", "source_mode", "image_urls_raw"]].copy()
    for column in ("article", "client_code", "source_mode", "image_urls_raw"):
        prepared[column] = prepared[column].fillna("").astype(str).str.strip()

    prepared["source_mode"] = prepared.apply(infer_source_mode, axis=1)
    prepared = prepared[prepared["client_code"] != ""]
    prepared = prepared[
        (
            (prepared["source_mode"] == "catalog") & (prepared["article"] != "")
        )
        | (
            (prepared["source_mode"] == "links") & (prepared["image_urls_raw"] != "")
        )
    ]
    return prepared.reset_index(drop=True)


def infer_source_mode(row: pd.Series) -> str:
    raw_source = str(row.get("source_mode", "")).strip().lower()
    if raw_source in LINK_SOURCE_ALIASES:
        return "links"
    if raw_source in CATALOG_SOURCE_ALIASES:
        return "catalog"

    if str(row.get("image_urls_raw", "")).strip():
        return "links"
    return "catalog"


def build_client_export(client_key: str, mapping_df: pd.DataFrame) -> tuple[bytes, list[ExportRowResult]]:
    profile = get_client_profile(client_key)
    report_rows: list[ExportRowResult] = []
    output = io.BytesIO()

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for _, row in mapping_df.iterrows():
            article = row["article"]
            client_code = row["client_code"]
            product = fetch_product_by_article(article)
            if not product:
                report_rows.append(
                    ExportRowResult(article, client_code, "error", "Товар не найден в локальной базе", 0)
                )
                continue

            images = fetch_product_images(product["id"])
            if not images:
                report_rows.append(
                    ExportRowResult(article, client_code, "error", "У товара нет сохранённых изображений", 0)
                )
                continue

            max_images = int(profile.get("max_images", len(images)))
            exported_files = 0
            row_warnings: list[str] = []
            for index, image in enumerate(images[:max_images], start=1):
                file_path = Path(image["local_path"])
                if not file_path.exists():
                    continue
                file_bytes, extension, warnings = prepare_image_for_client(file_path, profile)
                file_name = build_client_file_name(profile, client_code, index, extension)
                archive.writestr(file_name, file_bytes)
                exported_files += 1
                row_warnings.extend(warnings)
            if row_warnings:
                message = "; ".join(dict.fromkeys(row_warnings))
            else:
                message = "OK" if exported_files else "Нет файлов для упаковки"
            report_rows.append(
                ExportRowResult(article, client_code, "ok" if exported_files else "warning", message, exported_files)
            )

        archive.writestr("report.csv", export_report_csv(report_rows))

    return output.getvalue(), report_rows


def build_client_export_from_upload(
    client_key: str,
    upload_df: pd.DataFrame,
) -> tuple[bytes, list[ExportRowResult]]:
    profile = get_client_profile(client_key)
    report_rows: list[ExportRowResult] = []
    output = io.BytesIO()

    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for _, row in upload_df.iterrows():
            article = str(row.get("article", "")).strip()
            client_code = str(row["client_code"]).strip()
            source_mode = str(row["source_mode"]).strip()
            raw_urls = str(row.get("image_urls_raw", "")).strip()

            if source_mode == "links":
                exported_files, message, status = export_link_row_to_archive(
                    archive,
                    profile,
                    article,
                    client_code,
                    raw_urls,
                )
                report_rows.append(
                    ExportRowResult(article, client_code, status, message, exported_files)
                )
                continue

            exported_files, message, status = export_catalog_row_to_archive(
                archive,
                profile,
                article,
                client_code,
            )
            report_rows.append(
                ExportRowResult(article, client_code, status, message, exported_files)
            )

        archive.writestr("report.csv", export_report_csv(report_rows))

    return output.getvalue(), report_rows


def build_catalog_export_from_upload(
    client_key: str,
    upload_df: pd.DataFrame,
) -> ClientExportArtifacts:
    catalog_rows = upload_df[upload_df["source_mode"] == "catalog"][["article", "client_code"]].copy()
    if catalog_rows.empty:
        return ClientExportArtifacts(None, [], 0)

    zip_bytes, report_rows = build_client_export(client_key, catalog_rows.reset_index(drop=True))
    return ClientExportArtifacts(zip_bytes, report_rows, len(catalog_rows.index))


def filter_upload_rows_for_client(client_key: str, upload_df: pd.DataFrame) -> pd.DataFrame:
    prepared = upload_df.copy()
    if client_key == "sportmaster":
        mask = prepared["client_code"].apply(is_valid_sportmaster_code)
        return prepared[mask].reset_index(drop=True)
    if client_key == "detmir":
        mask = prepared["client_code"].apply(is_valid_detmir_code)
        return prepared[mask].reset_index(drop=True)
    return prepared.reset_index(drop=True)


def is_valid_sportmaster_code(value: str) -> bool:
    normalized = str(value).strip()
    if not normalized or len(normalized) > 64:
        return False
    return bool(SPORTMASTER_CODE_PATTERN.fullmatch(normalized))


def is_valid_detmir_code(value: str) -> bool:
    normalized = str(value).strip()
    if not normalized or len(normalized) > 128:
        return False
    if not DETMIR_CODE_PATTERN.fullmatch(normalized):
        return False
    return any(character.isdigit() for character in normalized)


def build_client_file_name(profile: dict[str, Any], client_code: str, index: int, extension: str) -> str:
    padding = int(profile.get("index_padding", 1))
    index_value = str(index).zfill(padding)
    file_stem = profile["file_name_template"].format(client_code=client_code, index=index_value)
    folder_name = sanitize_archive_component(client_code)
    return f"{folder_name}/{file_stem}.{extension}"


def sanitize_archive_component(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]+', "_", value.strip())
    return sanitized or "item"


def export_catalog_row_to_archive(
    archive: zipfile.ZipFile,
    profile: dict[str, Any],
    article: str,
    client_code: str,
) -> tuple[int, str, str]:
    product = fetch_product_by_article(article)
    if not product:
        return 0, "Товар не найден в локальной базе", "error"

    images = fetch_product_images(product["id"])
    if not images:
        return 0, "У товара нет сохранённых изображений", "error"

    max_images = int(profile.get("max_images", len(images)))
    exported_files = 0
    row_warnings: list[str] = []
    for index, image in enumerate(images[:max_images], start=1):
        file_path = Path(image["local_path"])
        if not file_path.exists():
            continue
        file_bytes, extension, warnings = prepare_image_for_client(file_path, profile)
        file_name = build_client_file_name(profile, client_code, index, extension)
        archive.writestr(file_name, file_bytes)
        exported_files += 1
        row_warnings.extend(warnings)

    if row_warnings:
        return exported_files, "; ".join(dict.fromkeys(row_warnings)), "ok" if exported_files else "warning"
    return exported_files, "OK" if exported_files else "Нет файлов для упаковки", "ok" if exported_files else "warning"


def export_link_row_to_archive(
    archive: zipfile.ZipFile,
    profile: dict[str, Any],
    article: str,
    client_code: str,
    raw_urls: str,
) -> tuple[int, str, str]:
    row_warnings: list[str] = []
    candidates = collect_link_candidates(raw_urls, row_warnings)
    if not candidates:
        message = "; ".join(dict.fromkeys(row_warnings)) if row_warnings else "Не удалось получить изображения из указанных ссылок"
        return 0, message, "warning"

    max_images = int(profile.get("max_images", len(candidates)))
    exported_files = 0

    for index, candidate in enumerate(candidates[:max_images], start=1):
        try:
            file_bytes, extension, warnings = prepare_remote_image_for_client(candidate.source_url, profile)
        except requests.RequestException as exc:
            row_warnings.append(f"Не удалось скачать фото {index}: {exc}")
            continue
        except OSError:
            row_warnings.append(f"Ссылка {index} не содержит корректное изображение")
            continue

        file_name = build_client_file_name(profile, client_code, index, extension)
        archive.writestr(file_name, file_bytes)
        exported_files += 1
        row_warnings.extend(warnings)

    if not exported_files:
        message = "; ".join(dict.fromkeys(row_warnings)) if row_warnings else "Не удалось скачать ни одного фото"
        return 0, message, "warning"

    if row_warnings:
        return exported_files, "; ".join(dict.fromkeys(row_warnings)), "ok"
    return exported_files, "OK", "ok"


def collect_link_candidates(raw_urls: str, row_warnings: list[str]) -> list[Any]:
    candidates: list[Any] = []
    seen_urls: set[str] = set()
    for url in split_reference_urls(raw_urls):
        if is_generic_image_search_url(url):
            row_warnings.append("Ссылки из общих поисковиков по картинкам пропущены: используйте прямые URL или страницы поставщика.")
            continue
        for candidate in parse_direct_image_urls(url):
            if candidate.source_url in seen_urls:
                continue
            seen_urls.add(candidate.source_url)
            candidates.append(candidate)
    return candidates


def is_generic_image_search_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    return (
        ("yandex." in host and path.startswith("/images/search"))
        or ("google." in host and "/search" in path)
        or ("bing.com" in host and "/images/search" in path)
        or ("duckduckgo.com" in host and path.startswith("/"))
    )


def prepare_remote_image_for_client(
    source_url: str,
    profile: dict[str, Any],
) -> tuple[bytes, str, list[str]]:
    download_url = resolve_download_url(source_url)
    response = download_remote_response(download_url, source_url)
    content = response.content
    content_type = response.headers.get("Content-Type")

    extension = infer_extension(source_url, content_type, content)
    with Image.open(BytesIO(content)) as image:
        warnings: list[str] = []
        allowed_extensions = {ext.lower() for ext in profile.get("allowed_extensions", ["jpg"])}
        target_extension = extension if extension in allowed_extensions else (
            "jpg" if "jpg" in allowed_extensions else sorted(allowed_extensions)[0]
        )

        working_image = image.convert("RGB") if target_extension in {"jpg", "jpeg"} else image.copy()
        long_side = max(working_image.size)
        min_long_side = profile.get("min_long_side_px")
        max_long_side = profile.get("max_long_side_px")
        if min_long_side and long_side < min_long_side:
            warnings.append(f"Изображение меньше рекомендуемой длинной стороны {min_long_side}px")
        if max_long_side and long_side > max_long_side:
            working_image.thumbnail((max_long_side, max_long_side))

        max_file_size_mb = profile.get("max_file_size_mb")
        max_file_size_bytes = int(max_file_size_mb * 1024 * 1024) if max_file_size_mb else None
        file_bytes, final_extension = serialize_image_for_client(
            working_image,
            target_extension,
            allowed_extensions,
            max_file_size_bytes,
        )
        if max_file_size_bytes and len(file_bytes) > max_file_size_bytes:
            warnings.append(f"Файл превышает лимит {max_file_size_mb} МБ")
        return file_bytes, final_extension, warnings


def download_remote_response(download_url: str, source_url: str) -> requests.Response:
    response = requests.get(download_url, headers=request_headers(), timeout=20)
    try:
        response.raise_for_status()
        return response
    except requests.HTTPError:
        if response.status_code != 403:
            raise

    parsed = urlparse(source_url)
    referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme and parsed.netloc else source_url
    headers = {
        **request_headers(),
        "Referer": referer,
        "Origin": f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else referer,
    }
    retry_response = requests.get(download_url, headers=headers, timeout=20)
    retry_response.raise_for_status()
    return retry_response



def prepare_image_for_client(file_path: Path, profile: dict[str, Any]) -> tuple[bytes, str, list[str]]:
    warnings: list[str] = []
    allowed_extensions = {extension.lower() for extension in profile.get("allowed_extensions", ["jpg"])}
    target_extension = file_path.suffix.lower().lstrip(".") or "jpg"
    if target_extension not in allowed_extensions:
        target_extension = "jpg" if "jpg" in allowed_extensions else sorted(allowed_extensions)[0]

    max_long_side = profile.get("max_long_side_px")
    min_long_side = profile.get("min_long_side_px")

    with Image.open(file_path) as image:
        image = image.convert("RGB") if target_extension in {"jpg", "jpeg"} else image.copy()
        long_side = max(image.size)
        if min_long_side and long_side < min_long_side:
            warnings.append(f"Изображение меньше рекомендуемой длинной стороны {min_long_side}px")
        if max_long_side and long_side > max_long_side:
            image.thumbnail((max_long_side, max_long_side))

        image_for_export = image.copy()

    max_file_size_mb = profile.get("max_file_size_mb")
    max_file_size_bytes = int(max_file_size_mb * 1024 * 1024) if max_file_size_mb else None
    file_bytes, target_extension = serialize_image_for_client(
        image_for_export,
        target_extension,
        allowed_extensions,
        max_file_size_bytes,
    )
    if max_file_size_bytes and len(file_bytes) > max_file_size_bytes:
        warnings.append(f"Файл превышает лимит {max_file_size_mb} МБ")
    return file_bytes, target_extension, warnings


def serialize_image_for_client(
    image: Image.Image,
    target_extension: str,
    allowed_extensions: set[str],
    max_file_size_bytes: int | None,
) -> tuple[bytes, str]:
    strategies: list[str] = []
    if target_extension in {"jpg", "jpeg"}:
        strategies.append("jpg")
    elif target_extension in allowed_extensions:
        strategies.append(target_extension)

    for fallback in ("jpg", "webp", "png"):
        if fallback in allowed_extensions and fallback not in strategies:
            strategies.append(fallback)

    best_bytes = b""
    best_extension = strategies[0] if strategies else "jpg"
    working_image = image.copy()

    while True:
        improved = False
        for extension in strategies:
            candidate_bytes = encode_image_bytes(working_image, extension)
            candidate_bytes = shrink_encoded_bytes_if_needed(
                working_image,
                extension,
                candidate_bytes,
                max_file_size_bytes,
            )
            if not best_bytes or len(candidate_bytes) < len(best_bytes):
                best_bytes = candidate_bytes
                best_extension = extension
            if not max_file_size_bytes or len(candidate_bytes) <= max_file_size_bytes:
                return candidate_bytes, extension
        if not max_file_size_bytes or max(working_image.size) <= 1000:
            return best_bytes, best_extension

        # If the file is still too large, gently scale it down and try again.
        new_width = max(int(working_image.size[0] * 0.9), 1)
        new_height = max(int(working_image.size[1] * 0.9), 1)
        if (new_width, new_height) == working_image.size:
            return best_bytes, best_extension
        working_image = working_image.resize((new_width, new_height))
        improved = True
        if not improved:
            return best_bytes, best_extension


def shrink_encoded_bytes_if_needed(
    image: Image.Image,
    extension: str,
    initial_bytes: bytes,
    max_file_size_bytes: int | None,
) -> bytes:
    if not max_file_size_bytes or len(initial_bytes) <= max_file_size_bytes:
        return initial_bytes

    if extension == "jpg":
        for quality in (85, 80, 75, 70, 65, 60, 55, 50):
            candidate = encode_image_bytes(image, extension, quality=quality)
            if len(candidate) <= max_file_size_bytes:
                return candidate
        return candidate

    if extension == "webp":
        for quality in (85, 80, 75, 70, 65, 60, 55, 50):
            candidate = encode_image_bytes(image, extension, quality=quality)
            if len(candidate) <= max_file_size_bytes:
                return candidate
        return candidate

    return initial_bytes


def encode_image_bytes(image: Image.Image, extension: str, quality: int = 90) -> bytes:
    buffer = io.BytesIO()
    if extension in {"jpg", "jpeg"}:
        working = image.convert("RGB")
        working.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()
    if extension == "png":
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()
    if extension == "webp":
        working = image.convert("RGB") if image.mode not in {"RGB", "RGBA"} else image
        working.save(buffer, format="WEBP", quality=quality, method=6)
        return buffer.getvalue()
    image.save(buffer, format=extension.upper())
    return buffer.getvalue()


def export_report_csv(rows: list[ExportRowResult]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["article", "client_code", "status", "message", "exported_files"])
    for row in rows:
        writer.writerow([row.article, row.client_code, row.status, row.message, row.exported_files])
    return output.getvalue()
