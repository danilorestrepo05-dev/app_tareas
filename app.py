"""Punto de entrada de la app web (Streamlit Community Cloud / local).

Ejecutar con:  streamlit run app.py
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="NotesControl",
    page_icon="assets/icon.svg",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from auth import auth as auth_mod
from repositories.local_json import LocalJsonRepository
from repositories.mirror import MirrorRepository
from services.job_service import JobService
from ui import components as cmp
from ui.styles import apply_styles

_LOGO_SVG = (Path(__file__).resolve().parent / "assets" / "icon.svg").read_text(encoding="utf-8")


@st.cache_resource(show_spinner=False)
def build_service(email: str) -> JobService:
    """Clave de caché por email: cada usuario lee/escribe solo su archivo."""
    path = auth_mod.data_path_for(email)
    primary = LocalJsonRepository(path)
    return JobService(MirrorRepository(primary))


def main() -> None:
    apply_styles()

    user = auth_mod.require_login()
    email = user["email"]

    if auth_mod.complete_drive_auth():
        st.rerun()

    service = build_service(email)

    # Conectar el respaldo de Drive (best-effort; nunca rompe la app).
    prev_error = getattr(service.repo, "last_error", None)
    service.repo.attach_mirror(auth_mod.get_drive_repository(email))
    if prev_error and not getattr(service.repo, "last_error", None):
        service.repo.last_error = prev_error

    # Ancla de destino para el botón "volver arriba".
    st.markdown('<span id="nc-top"></span>', unsafe_allow_html=True)

    # Barra superior: marca a la izquierda, usuario + salir a la derecha.
    h_left, h_right = st.columns([3, 1], vertical_alignment="center")
    with h_left:
        st.markdown(
            f'<div class="app-header">'
            f'<span class="app-logo">{_LOGO_SVG}</span>'
            f'<span class="app-brand">NotesControl</span>'
            '<div class="app-caption">Estados, horas, cobros y notas · con respaldo en tu Google Drive.</div>'
            "</div>",
            unsafe_allow_html=True,
        )
    with h_right:
        st.markdown(
            f'<div class="top-user">'
            f'<span class="top-user-name">👤 {user["name"]}</span>'
            f'<span class="top-user-mail">{email}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
        if st.button("Salir", key="btn_logout", type="secondary", use_container_width=True):
            auth_mod.logout()

    if getattr(service.repo, "last_error", None):
        st.warning(service.repo.last_error)

    cmp.bind_service(service)

    PAGES = ["Tablero", "Nuevo", "Bloc", "Recordatorios", "Historial", "Respaldo"]
    PAGE_ICONS = {
        "Tablero": ":material/dashboard:",
        "Nuevo": ":material/add_circle:",
        "Bloc": ":material/sticky_note_2:",
        "Recordatorios": ":material/notifications:",
        "Historial": ":material/history:",
        "Respaldo": ":material/cloud_done:",
    }
    # Navegación por saltos: "Ir al trabajo" limpia el widget y lo re-crea.
    go_page = st.session_state.pop("_go_page", None)
    if go_page is not None:
        st.session_state.pop("_page_nav", None)
    nav_default = go_page or st.session_state.get("_page_nav", "Tablero")
    page = st.segmented_control(
        "Navegación",
        PAGES,
        default=nav_default,
        key="_page_nav",
        format_func=lambda v: f"{PAGE_ICONS.get(v, '')} {v}".strip(),
        label_visibility="collapsed",
    )
    st.divider()

    if page == "Tablero":
        cmp.render_dashboard_tab()
    elif page == "Nuevo":
        cmp.render_new_job_form()
    elif page == "Bloc":
        cmp.render_notes_tab()
    elif page == "Recordatorios":
        cmp.render_reminders_tab()
    elif page == "Historial":
        cmp.render_history_tab()
    else:
        cmp.render_backup_panel(email)

    cmp.render_back_to_top(start_at_top=st.session_state.pop("_scroll_to_top", False))


if __name__ == "__main__":
    main()