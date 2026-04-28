from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from config import CLIENT_PROFILES_PATH, DB_PATH, EXPORTS_DIR, MEDIA_DIR, ensure_directories
from db import fetch_product_images, fetch_products, init_db
from services.catalog import load_dataframe, normalize_catalog_dataframe
from services.client_profiles import load_client_profiles
from services.export_service import build_client_export, normalize_mapping_dataframe
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
    st.sidebar.divider()
    st.sidebar.subheader("Клиенты")
    for key, profile in profiles.items():
        st.sidebar.markdown(
            f"**{profile['label']}**  \n"
            f"Код: `{key}`  \n"
            f"Имя файла: `{profile['file_name_template']}`"
        )


def render_catalog_tab() -> None:
    st.subheader("Поиск и сохранение фото")
    st.write(
        "Загрузите Excel/CSV менеджера с товарами. Поддерживаются поля: "
        "`артикул`, `название`, `шт`, `сайт`, `артикул поставщика`, "
        "`ссылка на товар`, `картинки`."
    )

    file = st.file_uploader(
        "Файл товаров",
        type=["csv", "xlsx", "xls"],
        key="catalog_uploader",
    )

    if file:
        dataframe = load_dataframe(file.name, file.getvalue())
        prepared = normalize_catalog_dataframe(dataframe)
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

    mapping_df = normalize_mapping_dataframe(load_dataframe(file.name, file.getvalue()))
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
