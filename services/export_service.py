from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from PIL import Image

from db import fetch_product_by_article, fetch_product_images
from services.client_profiles import get_client_profile


CLIENT_MAPPING_ALIASES = {
    "article": ("article", "артикул", "артикул товара", "sku"),
    "client_code": (
        "client_code",
        "client code",
        "код клиента",
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
    ),
}


@dataclass
class ExportRowResult:
    article: str
    client_code: str
    status: str
    message: str
    exported_files: int


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


def build_client_file_name(profile: dict[str, Any], client_code: str, index: int, extension: str) -> str:
    padding = int(profile.get("index_padding", 1))
    index_value = str(index).zfill(padding)
    file_stem = profile["file_name_template"].format(client_code=client_code, index=index_value)
    return f"{file_stem}.{extension}"


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
