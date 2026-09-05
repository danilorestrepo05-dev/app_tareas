"""Autenticación de identidad (``st.login("google")``) y autorización del
respaldo en Google Drive (scope ``drive.file``).

GOTCHA crítico: el login da identidad, pero NO acceso al Drive. El respaldo
usa un OAuth 2.0 propio (secrets ``[drive_oauth]``) que pide el scope de Drive
y guarda el token por usuario. Si no hay credenciales configuradas, la app cae
a un "modo desarrollo" local para poder ejecutarse sin Google.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from repositories.drive import (
    DRIVE_SCOPE,
    DriveNotAvailableError,
    DriveRepository,
    build_service,
)

CRED_DIR = ".credentials"
DEV_USER_KEY = "_dev_user"

try:
    _LOGO_SVG = (
        Path(__file__).resolve().parent.parent / "assets" / "icon.svg"
    ).read_text(encoding="utf-8")
except OSError:  # pragma: no cover - el logo vuela junto con el repo
    _LOGO_SVG = ""


def _user_cred_path(email: str) -> str:
    safe = hashlib.sha1(email.strip().lower().encode("utf-8")).hexdigest()
    return os.path.join(CRED_DIR, f"{safe}.json")


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
                " siempre a mano y respaldados en tu Google Drive.</div>"
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


# ---------------------------------------------------------------------------
# Respaldo en Drive (scope drive.file) - OAuth 2.0 propio
# ---------------------------------------------------------------------------
@dataclass
class DriveStatus:
    linked: bool = False
    needs_setup: bool = False
    auth_url: Optional[str] = None
    error: Optional[str] = None
    last_sync_error: Optional[str] = field(default=None)


def _drive_config() -> dict:
    import streamlit as st

    try:
        return dict(st.secrets.get("drive_oauth") or {})
    except Exception:
        return {}


def _build_flow(redirect_uri: str):
    from google_auth_oauthlib.flow import Flow

    cfg = _drive_config()
    client_config = {
        "web": {
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "auth_uri": cfg.get("auth_uri", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=[DRIVE_SCOPE])
    flow.redirect_uri = redirect_uri
    return flow


def drive_redirect_uri() -> str:
    cfg = _drive_config()
    return cfg.get("redirect_uri") or "http://localhost:8501"


def start_drive_auth(email: str) -> Optional[str]:
    """Genera la URL de autorización de Drive. Devuelve None si falta config."""
    import streamlit as st

    if not _drive_config():
        return None
    if not email:
        return None
    try:
        redirect_uri = drive_redirect_uri()
        flow = _build_flow(redirect_uri)
        auth_url, state = flow.authorization_url(
            access_type="offline", prompt="consent", include_granted_scopes="true"
        )
        st.session_state["_drive_oauth"] = {
            "email": email,
            "state": state,
            "redirect_uri": redirect_uri,
        }
        return auth_url
    except Exception as exc:  # pragma: no cover
        st.session_state["_drive_oauth_error"] = str(exc)
        return None


def complete_drive_auth() -> bool:
    """Intercambia el `code` del redirect por un token y lo guarda por usuario."""
    import streamlit as st

    params = st.query_params
    if "code" not in params:
        return False
    saved = st.session_state.get("_drive_oauth")
    if not saved:
        return False
    if params.get("state") != saved.get("state"):
        st.session_state["_drive_oauth_error"] = "Estado OAuth no válido."
        return False
    try:
        redirect_uri = saved["redirect_uri"]
        callback = (
            f"{redirect_uri}?code={params['code']}&state={params['state']}"
        )
        flow = _build_flow(redirect_uri)
        flow.fetch_token(authorization_response=callback)
        _save_token(saved["email"], flow.credentials)
        st.session_state.pop("_drive_oauth", None)
        st.session_state.pop("_drive_oauth_error", None)
        for key in list(params.keys()):
            if key in ("code", "scope", "authuser", "prompt", "state"):
                del st.query_params[key]
        return True
    except Exception as exc:  # pragma: no cover
        st.session_state["_drive_oauth_error"] = str(exc)
        return False


def _save_token(email: str, credentials) -> None:
    os.makedirs(CRED_DIR, exist_ok=True)
    with open(_user_cred_path(email), "w", encoding="utf-8") as fh:
        fh.write(credentials.to_json())


def _load_token(email: str):
    path = _user_cred_path(email)
    if not os.path.exists(path):
        return None
    try:
        from google.oauth2.credentials import Credentials

        with open(path, "r", encoding="utf-8") as fh:
            return Credentials.from_authorized_user_info(json.load(fh), scopes=[DRIVE_SCOPE])
    except Exception:
        return None


def _refresh_if_needed(email: str, credentials) -> "credentials":
    from google.auth.transport.requests import Request

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _save_token(email, credentials)
    return credentials


def get_drive_repository(email: str) -> Optional[DriveRepository]:
    """Devuelve un repositorio Drive listo, o None si no hay token/conexión."""
    creds = _load_token(email)
    if creds is None:
        return None
    try:
        creds = _refresh_if_needed(email, creds)
        service = build_service(creds)
        return DriveRepository(service)
    except Exception:
        return None


def unlink_drive(email: str) -> None:
    path = _user_cred_path(email)
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass