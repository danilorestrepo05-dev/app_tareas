"""Autenticación de identidad con ``st.login("google")``.

El email de sesión es la clave de partición de datos: cada usuario lee y
escribe solo su propio archivo. Si no hay credenciales en ``secrets.toml``,
la app cae a un "modo desarrollo" local para poder ejecutarse sin Google.
"""

from __future__ import annotations

import os
from pathlib import Path

DEV_USER_KEY = "_dev_user"

try:
    _LOGO_SVG = (
        Path(__file__).resolve().parent.parent / "assets" / "icon.svg"
    ).read_text(encoding="utf-8")
except OSError:  # pragma: no cover - el logo vuela junto con el repo
    _LOGO_SVG = ""


# ---------------------------------------------------------------------------
# Identidad (st.login "google")
# ---------------------------------------------------------------------------
def is_auth_configured() -> bool:
    try:
        import streamlit as st

        return bool(st.secrets.get("auth"))
    except Exception:
        return False


def require_login():
    """Devuelve dict {email, name, provider}. Bloquea hasta autenticar."""
    import streamlit as st

    if is_auth_configured():
        if not getattr(st.user, "is_logged_in", False):
            _render_login_screen(provider=True, st=st)
            st.stop()
        return {
            "email": str(getattr(st.user, "email", "") or ""),
            "name": str(getattr(st.user, "name", "") or "Usuario"),
            "provider": "google",
        }

    # Modo desarrollo (sin secrets OAuth): permite probar la app localmente.
    dev = st.session_state.get(DEV_USER_KEY)
    if not dev:
        _render_login_screen(provider=False, st=st)
        st.stop()
    return {**dev, "provider": "dev"}


def _render_login_screen(provider: bool, st) -> None:
    """Tarjeta de presentación + acceso (centrada, tipo landing móvil)."""
    c1, c2, c3 = st.columns([1, 1.35, 1])
    with c2:
        with st.container(border=True):
            st.markdown(
                '<div class="login-card">'
                f'<div class="login-logo">{_LOGO_SVG}</div>'
                '<div class="login-title">NotesControl</div>'
                '<div class="login-sub">Tus trabajos freelance: estados, horas, cobros y notas,'
                " siempre a mano y guardados en la nube.</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            if provider:
                if st.button("Iniciar sesión con Google", type="primary", key="login_google", use_container_width=True):
                    st.session_state["_scroll_to_top"] = True
                    try:
                        st.login("google")
                    except Exception as exc:  # pragma: no cover - depende del entorno
                        st.error(f"No se pudo iniciar el flujo OAuth: {exc}")
                st.caption("Usa tu cuenta de Google: tu email separa tus datos de los de otros usuarios.")
            else:
                with st.form("dev_login"):
                    email = st.text_input("Email (modo desarrollo)", value="dev@local.test")
                    name = st.text_input("Nombre", value="Usuario Dev")
                    submit = st.form_submit_button("Entrar", type="primary", use_container_width=True)
                if submit:
                    email = (email or "").strip()
                    st.session_state["_scroll_to_top"] = True
                    st.session_state[DEV_USER_KEY] = {
                        "email": email or "dev@local.test",
                        "name": (name or "").strip() or "Usuario Dev",
                    }
                    st.rerun()
                st.caption(
                    "Modo desarrollo: no hay credenciales OAuth en `secrets.toml`. "
                    "En producción se usará `st.login('google')`."
                )


def logout() -> None:
    import streamlit as st

    if is_auth_configured():
        st.logout()
    else:
        st.session_state.pop(DEV_USER_KEY, None)
        st.rerun()


def session_user_id(email: str) -> str:
    """Clave de partición de datos por email (minúsculas, sin espacios)."""
    return email.strip().lower()


def data_path_for(email: str) -> str:
    uid = session_user_id(email)
    root = os.environ.get("APP_DATA_ROOT", ".data")
    return os.path.join(root, uid, "trabajos.json")