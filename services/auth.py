from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote, urlencode, urlsplit, urlunsplit

import requests
import streamlit as st


YANDEX_AUTHORIZE_URL = "https://oauth.yandex.com/authorize"
YANDEX_TOKEN_URL = "https://oauth.yandex.com/token"
YANDEX_USERINFO_URL = "https://login.yandex.ru/info"
AUTH_COOKIE_NAME = "updatpic_auth"
AUTH_PENDING_COOKIE_NAME = "updatpic_auth_pending"
AUTH_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
AUTH_PENDING_COOKIE_MAX_AGE_SECONDS = 10 * 60


@dataclass
class AuthState:
    enabled: bool
    configured: bool
    required: bool
    login_url: str | None
    user: dict[str, Any] | None
    message: str | None = None


def auth_enabled() -> bool:
    return os.getenv("UPDATPIC_ENABLE_YANDEX_AUTH", "").strip().lower() in {"1", "true", "yes", "on"}


def auth_required() -> bool:
    return os.getenv("UPDATPIC_REQUIRE_LOGIN", "").strip().lower() in {"1", "true", "yes", "on"}


def yandex_auth_configured() -> bool:
    return all(
        [
            os.getenv("YANDEX_CLIENT_ID"),
            os.getenv("YANDEX_CLIENT_SECRET"),
            os.getenv("YANDEX_REDIRECT_URI"),
            os.getenv("UPDATPIC_AUTH_SECRET"),
        ]
    )


def get_auth_state() -> AuthState:
    enabled = auth_enabled()
    configured = yandex_auth_configured()
    required = auth_required()
    user = load_authenticated_user()
    login_url = build_login_url() if enabled and configured else None
    message = None
    if enabled and not configured:
        message = (
            "Yandex OAuth включён, но не настроен. Нужны переменные "
            "`YANDEX_CLIENT_ID`, `YANDEX_CLIENT_SECRET`, `YANDEX_REDIRECT_URI`, `UPDATPIC_AUTH_SECRET`."
        )
    return AuthState(
        enabled=enabled,
        configured=configured,
        required=required,
        login_url=login_url,
        user=user,
        message=message,
    )


def ensure_authentication() -> AuthState:
    handle_yandex_callback()
    state = get_auth_state()
    if state.required and state.enabled and not state.configured:
        render_login_gate(state)
        st.stop()
    if state.required and state.enabled and state.configured and not state.user:
        render_login_gate(state)
        st.stop()
    return state


def render_auth_sidebar(state: AuthState) -> None:
    st.sidebar.divider()
    st.sidebar.subheader("Авторизация")
    if state.message:
        st.sidebar.warning(state.message)

    if not state.enabled:
        st.sidebar.caption("Yandex OAuth выключен.")
        return

    if state.user:
        label = state.user.get("display_name") or state.user.get("login") or "Пользователь"
        st.sidebar.write(f"Вошли как: `{label}`")
        if state.user.get("email"):
            st.sidebar.caption(state.user["email"])
        if st.sidebar.button("Выйти", key="logout_yandex"):
            logout_user()
        return

    if not state.configured:
        st.sidebar.caption("Вход станет доступен после настройки ключей.")
        return

    if st.sidebar.button("Войти через Яндекс", key="login_yandex"):
        start_yandex_login()
        st.stop()

    st.sidebar.caption("Сессия хранится в браузере до 30 дней или до ручного выхода.")


def render_login_gate(state: AuthState) -> None:
    st.title("UpdatPic")
    st.subheader("Нужен вход")
    st.write("Для этого приложения включена обязательная авторизация через Яндекс.")
    if state.message:
        st.error(state.message)
        return
    if st.button("Войти через Яндекс", key="login_yandex_gate"):
        start_yandex_login()
        st.stop()


def start_yandex_login() -> None:
    pending_payload = build_pending_auth_payload()
    login_url = build_login_url(pending_payload)
    write_cookie(AUTH_PENDING_COOKIE_NAME, serialize_signed_payload(pending_payload), AUTH_PENDING_COOKIE_MAX_AGE_SECONDS)
    redirect_browser(login_url)


def handle_yandex_callback() -> None:
    if not auth_enabled() or not yandex_auth_configured():
        return

    query_params = st.query_params
    code = query_params.get("code")
    error = query_params.get("error")
    state = query_params.get("state")
    if not code and not error:
        return

    clear_query_params()

    if error:
        st.error(f"Яндекс OAuth вернул ошибку: {error}")
        clear_cookie(AUTH_PENDING_COOKIE_NAME)
        return

    pending = read_signed_cookie(AUTH_PENDING_COOKIE_NAME)
    if not pending:
        st.error("Сессия входа устарела. Попробуйте войти ещё раз.")
        return

    if pending.get("state") != state or pending.get("exp", 0) < time.time():
        st.error("Не удалось подтвердить вход через Яндекс. Попробуйте ещё раз.")
        clear_cookie(AUTH_PENDING_COOKIE_NAME)
        return

    try:
        token_payload = exchange_code_for_token(str(code), str(pending["code_verifier"]))
        user_payload = fetch_yandex_userinfo(token_payload["access_token"])
    except (requests.RequestException, ValueError) as exc:
        clear_cookie(AUTH_PENDING_COOKIE_NAME)
        st.error(f"Не удалось завершить вход через Яндекс: {exc}")
        return
    auth_payload = {
        "provider": "yandex",
        "user_id": user_payload.get("id", ""),
        "login": user_payload.get("login", ""),
        "email": user_payload.get("default_email", ""),
        "display_name": build_display_name(user_payload),
        "avatar_id": user_payload.get("default_avatar_id", ""),
        "exp": int(time.time()) + AUTH_COOKIE_MAX_AGE_SECONDS,
    }
    write_cookie(
        AUTH_COOKIE_NAME,
        serialize_signed_payload(auth_payload),
        AUTH_COOKIE_MAX_AGE_SECONDS,
    )
    clear_cookie(AUTH_PENDING_COOKIE_NAME)
    redirect_browser(current_app_url())
    st.stop()


def exchange_code_for_token(code: str, code_verifier: str) -> dict[str, Any]:
    response = requests.post(
        YANDEX_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": os.getenv("YANDEX_CLIENT_ID", ""),
            "client_secret": os.getenv("YANDEX_CLIENT_SECRET", ""),
            "code_verifier": code_verifier,
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    if "access_token" not in payload:
        raise ValueError(f"Не удалось получить OAuth токен: {payload}")
    return payload


def fetch_yandex_userinfo(access_token: str) -> dict[str, Any]:
    response = requests.get(
        YANDEX_USERINFO_URL,
        headers={"Authorization": f"OAuth {access_token}"},
        params={"format": "json"},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def build_login_url(pending: dict[str, Any] | None = None) -> str:
    pending = pending or build_pending_auth_payload()
    params = {
        "response_type": "code",
        "client_id": os.getenv("YANDEX_CLIENT_ID", ""),
        "redirect_uri": os.getenv("YANDEX_REDIRECT_URI", ""),
        "scope": os.getenv("YANDEX_SCOPE", "login:info login:email"),
        "state": pending["state"],
        "code_challenge": pending["code_challenge"],
        "code_challenge_method": "S256",
    }
    return f"{YANDEX_AUTHORIZE_URL}?{urlencode(params)}"


def build_pending_auth_payload() -> dict[str, Any]:
    code_verifier = secrets.token_urlsafe(48)
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("utf-8")).digest()).decode("utf-8").rstrip("=")
    return {
        "state": secrets.token_urlsafe(24),
        "code_verifier": code_verifier,
        "code_challenge": code_challenge,
        "exp": int(time.time()) + AUTH_PENDING_COOKIE_MAX_AGE_SECONDS,
    }


def build_display_name(user_payload: dict[str, Any]) -> str:
    first_name = str(user_payload.get("first_name", "")).strip()
    last_name = str(user_payload.get("last_name", "")).strip()
    if first_name or last_name:
        return " ".join(part for part in (first_name, last_name) if part)
    return str(user_payload.get("login", "")).strip()


def load_authenticated_user() -> dict[str, Any] | None:
    payload = read_signed_cookie(AUTH_COOKIE_NAME)
    if not payload:
        return None
    if payload.get("exp", 0) < time.time():
        return None
    return payload


def serialize_signed_payload(payload: dict[str, Any]) -> str:
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    token = base64.urlsafe_b64encode(payload_bytes).decode("utf-8").rstrip("=")
    signature = hmac.new(get_auth_secret().encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{token}.{signature}"


def deserialize_signed_payload(token: str) -> dict[str, Any] | None:
    try:
        payload_token, signature = token.rsplit(".", 1)
    except ValueError:
        return None
    expected_signature = hmac.new(
        get_auth_secret().encode("utf-8"),
        payload_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None
    padding = "=" * (-len(payload_token) % 4)
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_token + padding)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def get_auth_secret() -> str:
    secret = os.getenv("UPDATPIC_AUTH_SECRET", "").strip()
    if not secret:
        raise ValueError("UPDATPIC_AUTH_SECRET is not configured.")
    return secret


def read_signed_cookie(cookie_name: str) -> dict[str, Any] | None:
    raw_value = st.context.cookies.get(cookie_name)
    if not raw_value:
        return None
    return deserialize_signed_payload(unquote(raw_value))


def clear_auth_cookie() -> None:
    clear_cookie(AUTH_COOKIE_NAME)


def logout_user() -> None:
    clear_cookie(AUTH_COOKIE_NAME)
    clear_cookie(AUTH_PENDING_COOKIE_NAME)
    redirect_browser(current_app_url())
    st.stop()


def write_cookie(name: str, value: str, max_age_seconds: int) -> None:
    cookie_value = json.dumps(value)
    st.html(
        f"""
        <script>
        (function() {{
            const secure = window.location.protocol === "https:" ? "; Secure" : "";
            document.cookie = "{name}=" + encodeURIComponent({cookie_value}) + "; path=/; max-age={max_age_seconds}; SameSite=Lax" + secure;
        }})();
        </script>
        """
    )


def clear_cookie(name: str) -> None:
    st.html(
        f"""
        <script>
        (function() {{
            const secure = window.location.protocol === "https:" ? "; Secure" : "";
            document.cookie = "{name}=; path=/; max-age=0; SameSite=Lax" + secure;
        }})();
        </script>
        """
    )


def redirect_browser(url: str) -> None:
    st.html(
        f"""
        <script>
        window.location.href = {json.dumps(url)};
        </script>
        """
    )


def clear_query_params() -> None:
    for key in list(st.query_params.keys()):
        del st.query_params[key]


def current_app_url() -> str:
    url = st.context.url
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
