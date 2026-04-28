from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from config import AI_SETTINGS_PATH, CLIENT_PROFILES_PATH, DB_PATH, EXPORTS_DIR, MEDIA_DIR, TEMPLATES_DIR, ensure_directories
from services.ai_provider import (
    MODEL_PRESETS,
    check_provider_connection,
    current_status_label,
    load_ai_settings,
    mask_api_key,
    save_ai_settings,
    update_ai_settings,
)
from db import fetch_product_images, fetch_products, init_db
from services.auth import ensure_authentication, render_auth_sidebar
from services.catalog import REQUIRED_COLUMNS, load_best_matching_dataframe, normalize_catalog_dataframe
from services.client_profiles import load_client_profiles
from services.export_service import (
    CLIENT_UPLOAD_ALIASES,
    build_client_export_from_upload,
    filter_upload_rows_for_client,
    normalize_client_upload_dataframe,
)
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
    ai_settings = load_ai_settings()
    ai_status_level, ai_status_label = current_status_label(ai_settings)
    st.sidebar.title("UpdatPic")
    st.sidebar.caption("Сбор, хранение и клиентская выгрузка фото.")
    st.sidebar.write(f"База: `{DB_PATH}`")
    st.sidebar.write(f"Медиа: `{MEDIA_DIR}`")
    st.sidebar.write(f"Профили клиентов: `{CLIENT_PROFILES_PATH}`")
    st.sidebar.write(f"AI-настройки: `{AI_SETTINGS_PATH}`")
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
    st.sidebar.divider()
    st.sidebar.subheader("AI")
    st.sidebar.write(f"Провайдер: `{ai_settings['provider_label']}`")
    st.sidebar.write(f"Модель: `{ai_settings['model']}`")
    st.sidebar.write(f"Ключ: `{mask_api_key(str(ai_settings.get('api_key', '')))}`")
    if ai_status_level == "success":
        st.sidebar.success(ai_status_label)
    elif ai_status_level == "error":
        st.sidebar.error(ai_status_label)
    else:
        st.sidebar.warning(ai_status_label)
    if ai_settings.get("last_check_message"):
        st.sidebar.caption(ai_settings["last_check_message"])
    if ai_settings.get("last_check_at"):
        st.sidebar.caption(f"Последняя проверка: {ai_settings['last_check_at']}")
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
        "Если ссылки уже есть, заполните код клиента и колонку со ссылками. "
        "На выходе сервис собирает один ZIP-архив с готовыми файлами."
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
        zip_bytes, report_rows = build_client_export_from_upload(client_key, upload_df)
        combined_rows = [
            {
                "source_mode": upload_df.iloc[index]["source_mode"] if index < len(upload_df.index) else "",
                "article": row.article,
                "client_code": row.client_code,
                "status": row.status,
                "message": row.message,
                "exported_files": row.exported_files,
            }
            for index, row in enumerate(report_rows)
        ]

        if combined_rows:
            st.success("Выгрузка подготовлена.")
            st.dataframe(pd.DataFrame(combined_rows), use_container_width=True)
        else:
            st.warning("В файле не нашлось строк для выгрузки.")

        if zip_bytes:
            st.download_button(
                label="Скачать ZIP архива фото",
                data=zip_bytes,
                file_name=f"{client_key}_photos.zip",
                mime="application/zip",
            )


def render_ai_tab() -> None:
    st.subheader("AI-провайдер")
    st.write(
        "Здесь можно подключить OpenAI-compatible провайдер, например NVIDIA NIM. "
        "Ключ и модель сохраняются на стороне сервиса, чтобы команда сразу видела статус подключения."
    )
    st.warning(
        "API key, который уже был вставлен в переписку, лучше перевыпустить у провайдера. "
        "Я не записываю его в код репозитория."
    )

    settings = load_ai_settings()
    status_level, status_label = current_status_label(settings)

    with st.form("ai_provider_settings"):
        model_options = MODEL_PRESETS
        preset_index = model_options.index(settings["model"]) if settings["model"] in model_options else 0
        preset_model = st.selectbox("Пресет модели", options=model_options, index=preset_index)
        model_value = st.text_input("Model ID", value=settings["model"] or preset_model)
        base_url = st.text_input("Base URL", value=settings["base_url"])
        api_key = st.text_input("API key", value=settings.get("api_key", ""), type="password")
        temperature = st.slider("Temperature", 0.0, 2.0, float(settings.get("temperature", 0.2)), 0.05)
        top_p = st.slider("Top P", 0.0, 1.0, float(settings.get("top_p", 0.95)), 0.01)
        max_tokens = st.number_input("Max tokens для теста", min_value=16, max_value=8192, value=int(settings.get("max_tokens", 128)), step=16)
        save_clicked = st.form_submit_button("Сохранить настройки", type="primary")

    if save_clicked:
        settings = update_ai_settings(
            base_url=base_url,
            model=model_value or preset_model,
            api_key=api_key,
            temperature=temperature,
            top_p=top_p,
            max_tokens=int(max_tokens),
        )
        st.success("AI-настройки сохранены.")
        status_level, status_label = current_status_label(settings)

    action_columns = st.columns(2)
    with action_columns[0]:
        if st.button("Проверить ключ и модель", type="primary"):
            result = check_provider_connection(load_ai_settings())
            if result.ok:
                st.success(result.message)
            else:
                st.error(result.message)
            settings = load_ai_settings()
            status_level, status_label = current_status_label(settings)
    with action_columns[1]:
        if st.button("Сбросить последнее состояние проверки"):
            settings = load_ai_settings()
            settings["last_check_ok"] = None
            settings["last_check_message"] = "Проверка сброшена вручную."
            settings["last_check_at"] = ""
            save_ai_settings(settings)
            st.info("Статус проверки сброшен.")
            settings = load_ai_settings()
            status_level, status_label = current_status_label(settings)

    if status_level == "success":
        st.success(status_label)
    elif status_level == "error":
        st.error(status_label)
    else:
        st.warning(status_label)

    st.write(f"Провайдер: `{settings['provider_label']}`")
    st.write(f"Base URL: `{settings['base_url']}`")
    st.write(f"Model: `{settings['model']}`")
    st.write(f"Ключ: `{mask_api_key(str(settings.get('api_key', '')))}`")
    if settings.get("last_check_message"):
        st.caption(settings["last_check_message"])
    if settings.get("last_check_at"):
        st.caption(f"Последняя проверка: `{settings['last_check_at']}`")

    st.info(
        "Менять модель можно прямо здесь. "
        "Автоматически подставлять новые API key система не должна: это лучше оставлять ручным действием по соображениям безопасности."
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
    tab_catalog, tab_clients, tab_ai = st.tabs(["Каталог фото", "Клиенты", "AI"])
    with tab_catalog:
        render_catalog_tab()
    with tab_clients:
        render_clients_tab()
    with tab_ai:
        render_ai_tab()


if __name__ == "__main__":
    main()
