from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from config import CLIENT_PROFILES_PATH, DB_PATH, EXPORTS_DIR, MEDIA_DIR, TEMPLATES_DIR, ensure_directories
from db import fetch_product_images, fetch_products, init_db
from services.catalog import REQUIRED_COLUMNS, load_best_matching_dataframe, load_dataframe, normalize_catalog_dataframe
from services.client_profiles import load_client_profiles
from services.export_service import CLIENT_MAPPING_ALIASES, build_client_export, normalize_mapping_dataframe
from services.photo_pipeline import ingest_and_collect


st.set_page_config(
    page_title="UpdatPic",
    page_icon="🖼️",
    layout="wide",
)


def bootstrap() -> None:
    ensure_directories()
    init_db()


def render_sidebar() -> None:
    profiles = load_client_profiles()
    st.sidebar.title("UpdatPic")
    st.sidebar.caption("Сбор, хранение и клиентская выгрузка фото.")
    st.sidebar.write(f"База: `{DB_PATH}`")
    st.sidebar.write(f"Медиа: `{MEDIA_DIR}`")
    st.sidebar.write(f"Профили клиентов: `{CLIENT_PROFILES_PATH}`")
    st.sidebar.write(f"Архивы: `{EXPORTS_DIR}`")
    st.sidebar.write(f"Шаблоны: `{TEMPLATES_DIR}`")
    st.sidebar.divider()
    st.sidebar.subheader("Клиенты")
    for key, profile in profiles.items():
        st.sidebar.markdown(
            f"**{profile['label']}**  \n"
            f"Код: `{key}`  \n"
            f"Имя файла: `{profile['file_name_template']}`"
        )


def render_template_download(template_name: str, label: str, help_text: str) -> None:
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        st.warning(f"Шаблон `{template_name}` не найден. Сначала сгенерируйте его через `node scripts/build_templates.mjs`.")
        return
    st.download_button(
        label=label,
        data=template_path.read_bytes(),
        file_name=template_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        help=help_text,
    )


def render_catalog_tab() -> None:
    st.subheader("Поиск и сохранение фото")
    st.write(
        "Загрузите Excel/CSV менеджера с товарами. Поддерживаются поля: "
        "`артикул`, `название`, `шт`, `сайт`, `артикул поставщика`, "
        "`ссылка на товар`, `картинки`."
    )
    render_template_download(
        "manager_import_template.xlsx",
        "Скачать шаблон менеджера",
        "Готовый Excel для загрузки товаров и поиска фото.",
    )

    file = st.file_uploader(
        "Файл товаров",
        type=["csv", "xlsx", "xls"],
        key="catalog_uploader",
    )

    if file:
        try:
            dataframe, sheet_name = load_best_matching_dataframe(
                file.name,
                file.getvalue(),
                {**REQUIRED_COLUMNS},
            )
            prepared = normalize_catalog_dataframe(dataframe)
        except ValueError as exc:
            st.error(f"Не удалось разобрать файл товаров: {exc}")
            st.info("Проверьте, что в файле есть колонки `article` и `name` или их русские аналоги.")
            return

        if sheet_name != file.name:
            st.caption(f"Использован лист Excel: `{sheet_name}`")
        st.dataframe(prepared, use_container_width=True)

        limit = st.slider("Сколько фото максимум сохранять на товар", 1, 20, 10)
        if st.button("Собрать и сохранить фото", type="primary"):
            progress = st.progress(0)
            results: list[dict] = []
            total = len(prepared.index)
            for index, row in enumerate(prepared.to_dict(orient="records"), start=1):
                result = ingest_and_collect(row, limit=limit)
                results.append(
                    {
                        "article": row["article"],
                        "name": row["name"],
                        "candidates": result["candidate_count"],
                        "downloaded": result["downloaded_count"],
                    }
                )
                progress.progress(index / total)
            st.success("Сбор фото завершён.")
            st.dataframe(pd.DataFrame(results), use_container_width=True)

    st.divider()
    st.subheader("Локальный каталог")
    products = fetch_products()
    if not products:
        st.info("В базе пока нет товаров.")
        return

    catalog_df = pd.DataFrame(products)
    st.dataframe(
        catalog_df[["article", "name", "supplier_site", "image_count", "updated_at"]],
        use_container_width=True,
    )

    selected_article = st.selectbox(
        "Предпросмотр сохранённых фото",
        options=[product["article"] for product in products],
        index=0,
    )
    selected_product = next(product for product in products if product["article"] == selected_article)
    images = fetch_product_images(selected_product["id"])
    if not images:
        st.warning("Для выбранного товара нет сохранённых изображений.")
        return

    columns = st.columns(4)
    for index, image in enumerate(images):
        column = columns[index % len(columns)]
        column.image(
            image["local_path"],
            caption=f"{Path(image['local_path']).name} | {image['width_px']}x{image['height_px']}",
            use_container_width=True,
        )


def render_clients_tab() -> None:
    profiles = load_client_profiles()
    st.subheader("Клиентские выгрузки")
    render_template_download(
        "client_mapping_template.xlsx",
        "Скачать шаблон клиента",
        "Готовый Excel для сопоставления артикула и кода клиента.",
    )
    template_col_1, template_col_2 = st.columns(2)
    with template_col_1:
        render_template_download(
            "sportmaster_upload_template.xlsx",
            "Шаблон Спортмастер",
            "Excel-шаблон с колонкой `Код цветомодели` и памяткой по формату Спортмастера.",
        )
    with template_col_2:
        render_template_download(
            "detmir_upload_template.xlsx",
            "Шаблон Детский Мир",
            "Excel-шаблон с колонкой `Штрихкод товара` и памяткой по формату Детского Мира.",
        )
    client_key = st.selectbox(
        "Клиент",
        options=list(profiles.keys()),
        format_func=lambda key: profiles[key]["label"],
    )
    profile = profiles[client_key]
    st.caption(f"Источник правил: {profile.get('source_reference', 'не указан')}")
    for note in profile.get("notes", []):
        st.write(f"- {note}")

    file = st.file_uploader(
        "Файл соответствия товара и клиентского кода",
        type=["csv", "xlsx", "xls"],
        key="client_mapping_uploader",
    )
    if not file:
        return

    try:
        dataframe, sheet_name = load_best_matching_dataframe(
            file.name,
            file.getvalue(),
            CLIENT_MAPPING_ALIASES,
        )
        mapping_df = normalize_mapping_dataframe(dataframe)
    except ValueError as exc:
        st.error(f"Не удалось разобрать клиентский файл: {exc}")
        st.info(
            "Ожидаются колонки `article` и `client_code`. "
            "Если это Excel с несколькими листами, сервис попробует выбрать лучший лист автоматически."
        )
        return

    if sheet_name != file.name:
        st.caption(f"Использован лист Excel: `{sheet_name}`")
    st.dataframe(mapping_df, use_container_width=True)

    if st.button("Собрать архив для клиента", type="primary"):
        zip_bytes, report_rows = build_client_export(client_key, mapping_df)
        st.success("Архив подготовлен.")
        st.dataframe(pd.DataFrame([row.__dict__ for row in report_rows]), use_container_width=True)
        st.download_button(
            label="Скачать ZIP",
            data=zip_bytes,
            file_name=f"{client_key}_photos.zip",
            mime="application/zip",
        )


def main() -> None:
    bootstrap()
    render_sidebar()
    st.title("UpdatPic")
    st.caption(
        "Сервис для поиска фото по артикулу и сайту поставщика, локального хранения "
        "и выгрузки архивов под требования клиентов."
    )
    tab_catalog, tab_clients = st.tabs(["Каталог фото", "Клиенты"])
    with tab_catalog:
        render_catalog_tab()
    with tab_clients:
        render_clients_tab()


if __name__ == "__main__":
    main()
