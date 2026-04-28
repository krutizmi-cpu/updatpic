from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config import CLIENT_PROFILES_PATH, DB_PATH, EXPORTS_DIR, MEDIA_DIR, TEMPLATES_DIR, ensure_directories
from db import fetch_product_images, fetch_products, init_db
from services.auth import ensure_authentication, render_auth_sidebar
from services.catalog import REQUIRED_COLUMNS, load_best_matching_dataframe, normalize_catalog_dataframe
from services.client_profiles import load_client_profiles
from services.export_service import (
    CLIENT_UPLOAD_ALIASES,
    build_catalog_export_from_upload,
    filter_upload_rows_for_client,
    normalize_client_upload_dataframe,
)
from services.link_export import build_marketplace_link_export
from services.photo_pipeline import ingest_and_collect


st.set_page_config(
    page_title="UpdatPic",
    page_icon="🖼️",
    layout="wide",
)


def bootstrap() -> None:
    ensure_directories()
    init_db()


def render_sidebar(auth_state) -> None:
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
    render_auth_sidebar(auth_state)


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
    st.caption(
        "Для прямых фото лучше указывать открытые ссылки на сами файлы. "
        "Для Спортмастера держите порядок ссылок как нужно в карточке и разделяйте их `;`."
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
                try:
                    result = ingest_and_collect(row, limit=limit)
                    row_status = result["status"]
                    error_message = ""
                except Exception as exc:
                    result = {
                        "candidate_count": 0,
                        "downloaded_count": 0,
                        "existing_preserved_count": 0,
                        "status": "error",
                    }
                    row_status = "error"
                    error_message = str(exc)

                results.append(
                    {
                        "article": row["article"],
                        "name": row["name"],
                        "status": row_status,
                        "candidates": result["candidate_count"],
                        "downloaded": result["downloaded_count"],
                        "preserved_existing": result.get("existing_preserved_count", 0),
                        "error": error_message,
                    }
                )
                progress.progress(index / total)
            results_df = pd.DataFrame(results)
            success_count = int((results_df["status"] == "ok").sum())
            preserved_count = int((results_df["status"] == "preserved").sum())
            error_count = int((results_df["status"] == "error").sum())

            if error_count:
                st.warning(
                    f"Сбор завершён с ошибками: успешно {success_count}, "
                    f"сохранены старые фото {preserved_count}, ошибок {error_count}."
                )
            else:
                st.success(
                    f"Сбор фото завершён: успешно {success_count}, "
                    f"сохранены старые фото {preserved_count}."
                )
            st.dataframe(results_df, use_container_width=True)

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
    template_col_1, template_col_2 = st.columns(2)
    with template_col_1:
        render_template_download(
            "sportmaster_upload_template.xlsx",
            "Шаблон Спортмастер",
            "Один шаблон для двух сценариев: фото уже в каталоге или уже есть готовые ссылки.",
        )
    with template_col_2:
        render_template_download(
            "detmir_upload_template.xlsx",
            "Шаблон Детский Мир",
            "Один шаблон для двух сценариев: фото уже в каталоге или уже есть готовые ссылки.",
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
    st.info(
        "Один файл клиента поддерживает два режима: `каталог` и `ссылки`. "
        "Если фото уже спарсены в UpdatPic, заполните артикул и код клиента. "
        "Если ссылки уже есть, заполните код клиента и колонку со ссылками."
    )

    file = st.file_uploader(
        "Файл клиента",
        type=["csv", "xlsx", "xls"],
        key="client_mapping_uploader",
    )
    if not file:
        return

    try:
        dataframe, sheet_name = load_best_matching_dataframe(
            file.name,
            file.getvalue(),
            CLIENT_UPLOAD_ALIASES,
        )
        upload_df = normalize_client_upload_dataframe(dataframe)
        upload_df = filter_upload_rows_for_client(client_key, upload_df)
    except ValueError as exc:
        st.error(f"Не удалось разобрать клиентский файл: {exc}")
        st.info(
            "Ожидаются колонки с кодом клиента, а также артикул и/или ссылки на фото. "
            "Если это Excel с несколькими строками-инструкциями, сервис попробует сам найти строку заголовков."
        )
        return

    if sheet_name != file.name:
        st.caption(f"Использован лист Excel: `{sheet_name}`")
    st.dataframe(upload_df, use_container_width=True)

    mode_counts = upload_df["source_mode"].value_counts().to_dict()
    st.caption(
        f"Распознано строк: каталог `{mode_counts.get('catalog', 0)}`, "
        f"ссылки `{mode_counts.get('links', 0)}`."
    )

    if st.button("Подготовить выгрузку клиента", type="primary"):
        catalog_artifacts = build_catalog_export_from_upload(client_key, upload_df)
        link_rows = upload_df[upload_df["source_mode"] == "links"][
            ["article", "client_code", "image_urls_raw"]
        ].reset_index(drop=True)

        link_excel_bytes: bytes | None = None
        link_report_df = pd.DataFrame()
        if not link_rows.empty:
            link_excel_bytes, link_report_df = build_marketplace_link_export(client_key, link_rows)

        combined_rows: list[dict[str, object]] = []
        for row in catalog_artifacts.catalog_report_rows:
            combined_rows.append(
                {
                    "source_mode": "catalog",
                    "article": row.article,
                    "client_code": row.client_code,
                    "status": row.status,
                    "message": row.message,
                    "exported_files": row.exported_files,
                }
            )
        if not link_report_df.empty:
            for _, row in link_report_df.iterrows():
                combined_rows.append(
                    {
                        "source_mode": "links",
                        "article": row.get("article", ""),
                        "client_code": row["client_code"],
                        "status": row["status"],
                        "message": row["message"],
                        "exported_files": row["link_count"],
                    }
                )

        if combined_rows:
            st.success("Выгрузка подготовлена.")
            st.dataframe(pd.DataFrame(combined_rows), use_container_width=True)
        else:
            st.warning("В файле не нашлось строк для выгрузки.")

        download_columns = st.columns(2)
        with download_columns[0]:
            if catalog_artifacts.catalog_zip_bytes:
                st.download_button(
                    label="Скачать ZIP с локальными фото",
                    data=catalog_artifacts.catalog_zip_bytes,
                    file_name=f"{client_key}_photos.zip",
                    mime="application/zip",
                )
        with download_columns[1]:
            if link_excel_bytes:
                st.download_button(
                    label="Скачать Excel со ссылками",
                    data=link_excel_bytes,
                    file_name=f"{client_key}_ready_links.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )


def main() -> None:
    bootstrap()
    auth_state = ensure_authentication()
    render_sidebar(auth_state)
    st.title("UpdatPic")
    st.caption(
        "Сервис для поиска фото по артикулу и сайту поставщика, локального хранения "
        "и выгрузки архивов под требования клиентов."
    )
    if auth_state.user:
        st.caption(f"Текущий пользователь: {auth_state.user.get('display_name') or auth_state.user.get('login')}")
    tab_catalog, tab_clients = st.tabs(["Каталог фото", "Клиенты"])
    with tab_catalog:
        render_catalog_tab()
    with tab_clients:
        render_clients_tab()


if __name__ == "__main__":
    main()
