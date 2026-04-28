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

            exported_files = 0
            for index, image in enumerate(images, start=1):
                file_path = Path(image["local_path"])
                if not file_path.exists():
                    continue
                file_bytes, extension, warnings = prepare_image_for_client(file_path, profile)
                file_name = build_client_file_name(profile, client_code, index, extension)
                archive.writestr(file_name, file_bytes)
                exported_files += 1
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

        buffer = io.BytesIO()
        save_kwargs: dict[str, Any] = {}
        if target_extension in {"jpg", "jpeg"}:
            save_format = "JPEG"
            save_kwargs = {"quality": 90, "optimize": True}
            target_extension = "jpg"
        elif target_extension == "png":
            save_format = "PNG"
            save_kwargs = {"optimize": True}
        else:
            save_format = target_extension.upper()
        image.save(buffer, format=save_format, **save_kwargs)

    file_bytes = buffer.getvalue()
    max_file_size_mb = profile.get("max_file_size_mb")
    if max_file_size_mb and len(file_bytes) > max_file_size_mb * 1024 * 1024:
        warnings.append(f"Файл превышает лимит {max_file_size_mb} МБ")
    return file_bytes, target_extension, warnings


def export_report_csv(rows: list[ExportRowResult]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["article", "client_code", "status", "message", "exported_files"])
    for row in rows:
        writer.writerow([row.article, row.client_code, row.status, row.message, row.exported_files])
    return output.getvalue()
