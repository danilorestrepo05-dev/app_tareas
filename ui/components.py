"""Componentes reutilizables de la interfaz web (tarjetas compactas, tablero
por cliente, historial, recordatorios, bloc de notas, respaldo)."""

from __future__ import annotations

import json
from datetime import date
from typing import List, Optional

import streamlit as st
from streamlit.components.v1 import html as _components_html

from core.models import (
    JOB_TYPES,
    STATE_COMPLETADO,
    STATE_EN_PROGRESO,
    STATE_EN_PRODUCCION,
    STATE_LABELS,
    STATE_PENDIENTE,
    STATE_REALIZADO_PAGADO,
    TYPE_POR_HORA,
    TYPE_POR_SERVICIO,
    Job,
)
from services.job_service import JobError, JobService
from services.parser_notas import count_sections, parse
from repositories.github import GithubRepository

# Servicio activo de la sesión: app.py lo fija en cada ejecución.
service: JobService


def bind_service(svc: JobService) -> None:
    global service
    service = svc

STATE_COLORS = {
    STATE_PENDIENTE: ("#fbbf24", "rgba(245,158,11,0.16)"),
    STATE_EN_PROGRESO: ("#60a5fa", "rgba(59,130,246,0.18)"),
    STATE_COMPLETADO: ("#2dd4bf", "rgba(20,184,166,0.16)"),
    STATE_EN_PRODUCCION: ("#a78bfa", "rgba(139,92,246,0.18)"),
    STATE_REALIZADO_PAGADO: ("#34d399", "rgba(16,185,129,0.18)"),
}
TYPE_COLORS = {
    TYPE_POR_HORA: ("#38bdf8", "rgba(14,165,233,0.18)"),
    TYPE_POR_SERVICIO: ("#c084fc", "rgba(168,85,247,0.18)"),
}


def money(value: float) -> str:
    return f"${value:,.2f}"


def badge(text: str, color: str, bg: str) -> str:
    return f'<span class="badge" style="color:{color};background:{bg}">{text}</span>'


def job_badges(job: Job) -> str:
    st_fg, st_bg = STATE_COLORS.get(job.state, ("#cbd5e1", "rgba(148,163,184,0.15)"))
    t_fg, t_bg = TYPE_COLORS.get(job.job_type, ("#cbd5e1", "rgba(148,163,184,0.15)"))
    parts = [badge(job.state, st_fg, st_bg), badge(job.job_type, t_fg, t_bg)]
    if job.job_type == TYPE_POR_HORA:
        parts.append(badge(f"{job.inverted_hours:g} h", "#94a3b8", "rgba(148,163,184,0.15)"))
    return "".join(parts)


def _fecha(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    s = str(iso)[:10]
    try:
        y, m, d = s.split("-")
        return f"{d}/{m}/{y}"
    except ValueError:
        return s


def _overdue(job: Job) -> bool:
    if job.is_done:
        return False
    target = job.reminder_date or job.estimated_delivery
    if not target:
        return False
    try:
        return date.fromisoformat(str(target)[:10]) < date.today()
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Tablero: métricas + lista continua agrupada por cliente
# ---------------------------------------------------------------------------
def render_metrics(service: JobService) -> None:
    stats = service.stats()
    cols = st.columns(4)
    cols[0].metric("Trabajos", stats["total"])
    cols[1].metric("Activos", stats["active"])
    cols[2].metric("Facturado", money(stats["total_billed"]))
    cols[3].metric("Pendiente", money(stats["total_pending"]))


def render_dashboard_tab() -> None:
    focus_id = st.session_state.pop("_focus_job", None)
    render_metrics(service)
    st.divider()
    c1, c2, c3 = st.columns([1, 1, 2])
    state_filter = c1.selectbox("Estado", ["Todos"] + list(STATE_LABELS))
    type_filter = c2.selectbox("Tipo", ["Todos"] + list(JOB_TYPES))
    search = c3.text_input("Buscar cliente", placeholder="Filtrar por empresa…")

    jobs = service.list_jobs(
        state=None if state_filter == "Todos" else state_filter,
        job_type=None if type_filter == "Todos" else type_filter,
    )
    if search and search.strip():
        needle = search.strip().lower()
        jobs = [j for j in jobs if needle in j.client.lower()]

    if not jobs:
        st.info("No hay trabajos con estos filtros. Crea el primero en la pestaña ➕ Nuevo.")
        return

    default_view = state_filter == "Todos" and type_filter == "Todos" and not (search or "").strip()
    if default_view:
        pendientes = [
            j for j in jobs
            if j.state not in (STATE_EN_PRODUCCION, STATE_REALIZADO_PAGADO)
        ]
        completados = [
            j for j in jobs
            if j.state in (STATE_EN_PRODUCCION, STATE_REALIZADO_PAGADO)
        ]
        render_section("📌 Pendientes", service.group_by_client(pendientes), focus_id)
        render_section("✅ Completados", service.group_by_client(completados), focus_id)
    else:
        render_section("Resultados", service.group_by_client(jobs), focus_id)


def render_section(title: str, groups: List[tuple[str, List[Job]]], focus_id=None) -> None:
    st.subheader(title)
    if not groups:
        st.caption("Ninguno.")
        return
    for client, members in groups:
        subtotal = sum(j.subtotal() for j in members)
        st.markdown(
            f'<div class="client-bar">'
            f'<span class="client-name">🏢 {client}</span>'
            f'<span class="client-count">{len(members)} trabajo(s)</span>'
            f'<span class="client-total">{money(subtotal)}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        for job in members:
            render_job_card(job, focus_id=focus_id)


# ---------------------------------------------------------------------------
# Tarjeta compacta de trabajo
# ---------------------------------------------------------------------------
def render_job_card(job: Job, focus_id=None) -> None:
    meta = f"Creado: {_fecha(job.created_at)}"
    if job.estimated_delivery:
        meta += f" · Entrega: {_fecha(job.estimated_delivery)}"
    if job.reminder_date:
        meta += f" · Recordatorio: {_fecha(job.reminder_date)}"
    if job.completed_at:
        meta += f" · Completado: {_fecha(job.completed_at)}"
    if job.paid_at:
        meta += f" · Pagado: {_fecha(job.paid_at)}"
    if job.notes:
        meta += " · 📝"

    with st.container(border=True):
        head_l, head_r = st.columns([5, 2])
        with head_l:
            st.markdown(job_badges(job), unsafe_allow_html=True)
        with head_r:
            st.markdown(f'<div class="job-subtotal">{money(job.subtotal())}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="job-meta">{meta}</div>', unsafe_allow_html=True)
        if _overdue(job):
            st.markdown(
                '<span class="badge" style="color:#fca5a5;background:rgba(248,113,113,0.15)">⚠ Vencido</span>',
                unsafe_allow_html=True,
            )

        _render_state_control(job)

        with st.expander("⚙️ Editar · Notas", expanded=(job.id == focus_id)):
            render_job_admin(job)


def render_job_admin(job: Job) -> None:
    if job.is_editable:
        _render_edit_form(job)
    else:
        st.caption("Datos económicos congelados (costo y horas fijadas al Completar).")
    st.divider()
    _render_notes_section(job)
    _render_linked_notes(job)
    if st.button("🗑 Eliminar", key=f"borrar_{job.id}", type="secondary"):
        _confirm_delete(job.id)


def _render_state_control(job: Job) -> None:
    next_states = job.possible_states()
    prev_state = job.prev_state()
    if not next_states and not prev_state:
        if job.state == STATE_REALIZADO_PAGADO:
            st.html('<div class="job-done">✔ Trabajo terminado y cobrado</div>')
        return

    forward = next_states[0] if next_states else None
    if forward and prev_state:
        c_adv, c_back = st.columns(2)
        with c_adv:
            if st.button(
                f"▶ Avanzar a: {forward}",
                type="primary",
                use_container_width=True,
                key=f"adv_{job.id}",
            ):
                _do_advance(job, forward)
        with c_back:
            if st.button(
                f"◀ Volver a: {prev_state}",
                type="secondary",
                use_container_width=True,
                key=f"back_{job.id}",
            ):
                _do_regress(job, prev_state)
    elif forward:
        if st.button(
            f"▶ Avanzar a: {forward}",
            type="primary",
            use_container_width=True,
            key=f"adv_{job.id}",
        ):
            _do_advance(job, forward)
    else:
        if st.button(
            f"◀ Volver a: {prev_state}",
            type="secondary",
            use_container_width=True,
            key=f"back_{job.id}",
        ):
            _do_regress(job, prev_state)


def _do_advance(job: Job, target: str) -> None:
    try:
        service.advance(job.id, target)
        st.toast(f"'{job.client}' → {target}")
        st.rerun()
    except JobError as exc:
        st.error(str(exc))


def _do_regress(job: Job, prev_state: str) -> None:
    try:
        service.regress(job.id)
        st.toast(f"'{job.client}' volvió a {prev_state}.")
        st.rerun()
    except JobError as exc:
        st.error(str(exc))


def _as_date(iso: Optional[str]):
    if iso:
        try:
            return date.fromisoformat(str(iso)[:10])
        except ValueError:
            return None
    return None


def _render_edit_form(job: Job) -> None:
    with st.form(f"edit_{job.id}"):
        client = st.text_input("Cliente / Empresa", value=job.client)
        c1, c2 = st.columns(2)
        rate = hours = price = None
        if job.job_type == TYPE_POR_HORA:
            rate = c1.number_input("Tarifa por hora ($)", value=float(job.hourly_rate),
                                   min_value=0.0, step=0.5, format="%.2f")
            hours = c2.number_input("Horas invertidas", value=float(job.hours_invested),
                                    min_value=0.0, step=0.25, format="%.2f")
        else:
            price = c1.number_input("Precio fijo ($)", value=float(job.fixed_price),
                                    min_value=0.0, step=1.0, format="%.2f")
        c3, c4, c5 = st.columns(3)
        created = c3.date_input("Fecha de inicio",
                                value=_as_date(job.created_at) or date.today(),
                                key=f"creacion_{job.id}")
        delivery = c4.date_input("Entrega estimada", value=_as_date(job.estimated_delivery),
                                 key=f"entrega_{job.id}", help="Opcional")
        reminder = c5.date_input("Recordatorio", value=_as_date(job.reminder_date),
                                 key=f"record_{job.id}", help="Opcional")
        if st.form_submit_button("💾 Guardar cambios"):
            try:
                service.update_details(
                    job.id,
                    client=client,
                    hourly_rate=rate,
                    hours_invested=hours,
                    fixed_price=price,
                    estimated_delivery=delivery.isoformat() if delivery else None,
                    reminder_date=reminder.isoformat() if reminder else None,
                    created_at=created.isoformat() if created else None,
                )
                st.toast("Cambios guardados.")
                st.rerun()
            except JobError as exc:
                st.error(str(exc))


# ---------------------------------------------------------------------------
# Notas del trabajo (texto plano + vista previa con parser)
# ---------------------------------------------------------------------------
def _render_notes_section(job: Job) -> None:
    notas = job.notes or ""
    editing = st.session_state.get(f"_edit_notes_{job.id}", False)
    if editing:
        key = f"notas_{job.id}"
        with st.form(f"notas_{job.id}"):
            nuevo = st.text_area("Notas (pasos y código)", value=notas, height=170, key=key)
            if st.form_submit_button("💾 Guardar notas"):
                try:
                    service.update_notes(job.id, nuevo)
                    st.session_state.pop(f"_edit_notes_{job.id}", None)
                    st.toast("Notas guardadas.")
                    st.rerun()
                except JobError as exc:
                    st.error(str(exc))
        actual = st.session_state.get(key, notas)
        if st.checkbox("👁️ Vista previa (detecta pasos y código)", key=f"npv_{job.id}"):
            _render_preview(actual)
        if st.button("Cancelar", key=f"cnl_{job.id}"):
            st.session_state.pop(f"_edit_notes_{job.id}", None)
            st.rerun()
        return

    st.markdown("#### 📝 Notas y código")
    if notas.strip():
        _render_nota_blocks(notas)
    else:
        st.caption("Sin notas todavía.")
    if st.button("✏️ Editar notas", key=f"btn_edit_notes_{job.id}"):
        st.session_state[f"_edit_notes_{job.id}"] = True
        st.rerun()


def _render_preview(text: str) -> None:
    if not text or not text.strip():
        st.caption("Escribe algo para ver la detección.")
        return
    s = _nota_stats(text)
    st.caption(
        f"Detección automática: {s['titulos']} título(s) · {s['pasos']} bloque(s) "
        f"de pasos · {s['codigo']} bloque(s) de código"
    )
    _render_nota_blocks(text)


def _render_linked_notes(job: Job) -> None:
    linked = [
        service.get_note(nid)
        for nid in job.note_ids
        if nid in {n.id for n in service.list_notes()}
    ]
    if not linked:
        return
    st.markdown("#### 🔗 Notas enlazadas del bloc")
    for note in linked:
        with st.expander(note.title):
            _render_nota_blocks(note.content)
            if st.button("Desenlazar", key=f"unlink_{job.id}_{note.id}"):
                try:
                    service.unlink_note(job.id, note.id)
                    st.rerun()
                except JobError as exc:
                    st.error(str(exc))


@st.dialog("Confirmar eliminación")
def _confirm_delete(job_id: str) -> None:
    try:
        job = service.get_job(job_id)
    except JobError:
        st.warning("El trabajo ya no existe.")
        st.stop()
    st.write(f"¿Eliminar el trabajo de **{job.client}**? Esta acción no se puede deshacer.")
    c1, c2 = st.columns(2)
    if c1.button("Sí, eliminar", type="primary"):
        service.delete_job(job.id)
        st.toast("Trabajo eliminado.")
        st.rerun()
    if c2.button("Cancelar"):
        st.rerun()


# ---------------------------------------------------------------------------
# Nuevo trabajo
# ---------------------------------------------------------------------------
def render_new_job_form() -> None:
    st.subheader("Nuevo trabajo")
    with st.form("new_job"):
        client = st.text_input("Cliente / Empresa *", placeholder="Ej: Agencia XYZ")
        job_type = st.radio("Tipo de trabajo", list(JOB_TYPES), horizontal=True, index=0)
        if job_type == TYPE_POR_HORA:
            c1, c2 = st.columns(2)
            rate = c1.number_input("Tarifa por hora ($)", min_value=0.0, value=0.0,
                                   step=0.5, format="%.2f")
            hours = c2.number_input("Horas invertidas", min_value=0.0, value=0.0,
                                    step=0.25, format="%.2f")
            price = 0.0
        else:
            price = st.number_input("Precio fijo acordado ($)", min_value=0.0, value=0.0,
                                    step=1.0, format="%.2f")
            rate = hours = 0.0
        c3, c4, c5 = st.columns(3)
        created = c3.date_input("Fecha de inicio", value=date.today(), key="new_creacion")
        delivery = c4.date_input("Entrega estimada", value=None, key="new_delivery",
                                 help="Opcional")
        reminder = c5.date_input("Recordatorio", value=None, key="new_reminder",
                                 help="Opcional")
        notes = st.text_area("Notas (pasos por seguir y código)", height=120,
                             placeholder="Pega aquí tus apuntes del cuaderno…", key="new_notes")
        submitted = st.form_submit_button("➕ Crear trabajo", type="primary")

    pendientes = st.session_state.get("new_notes", "").strip()
    if st.checkbox("👁️ Vista previa de las notas (pasos/código)", key="new_notes_prev"):
        _render_preview(pendientes)

    if submitted:
        try:
            job = service.create_job(
                client=client,
                job_type=job_type,
                hourly_rate=rate,
                hours_invested=hours,
                fixed_price=price,
                estimated_delivery=delivery.isoformat() if delivery else None,
                reminder_date=reminder.isoformat() if reminder else None,
                notes=notes,
                created_at=created.isoformat() if created else None,
            )
            st.toast(f"Trabajo de '{job.client}' creado.")
            st.rerun()
        except JobError as exc:
            st.error(str(exc))


# ---------------------------------------------------------------------------
# Presentación de notas (parser)
# ---------------------------------------------------------------------------
def _nota_stats(text: str) -> dict:
    blocks = parse(text)
    return {
        "titulos": count_sections(text),
        "pasos": sum(1 for b in blocks if b["tipo"] == "pasos"),
        "codigo": sum(1 for b in blocks if b["tipo"] == "codigo"),
    }


def _render_nota_blocks(text: str) -> None:
    blocks = parse(text)
    if not blocks:
        st.caption("Contenido vacío.")
        return
    for block in blocks:
        if block["tipo"] == "titulo":
            st.markdown(f"##### {block['lineas'][0]}")
        elif block["tipo"] == "codigo":
            lang = "xml" if block["lineas"][0].lstrip().startswith("<") else "python"
            st.code("\n".join(block["lineas"]), language=lang)
        elif block["tipo"] == "pasos":
            for line in block["lineas"]:
                st.markdown(f"- {line}")
        else:
            for line in block["lineas"]:
                st.write(line)


# ---------------------------------------------------------------------------
# Botón flotante "volver arriba"
# ---------------------------------------------------------------------------
def render_back_to_top(start_at_top: bool = False) -> None:
    """Flecha ↑ fija (ancla nativa, sin JS) para subir al inicio.

    Un helper JS corre dentro de un iframe (`st.components.v1.html`), que es la
    única vía en Streamlit que ejecuta scripts (el pipeline de ``st.html``
    elimina ``<script>`` y atributos ``onclick``). El helper:
      - hace que el enlace deslice con suavidad el contenedor correcto;
      - al iniciar (login OAuth/desarrollo), reubica la página en el tope.
    """
    st.markdown(
        '<a id="return-to-top" href="#nc-top" aria-label="Volver arriba">↑</a>',
        unsafe_allow_html=True,
    )
    force_top = "1" if start_at_top else "0"
    _components_html(
        f"""
<script>
(function () {{
    var mom = window.parent;
    function cands() {{
        var list = [mom.document.scrollingElement, mom.document.documentElement, mom.document.body];
        ["stAppViewContainer", "stMain", "stMainBlockContainer", "stScrollToBottomContainer"]
            .forEach(function (id) {{
                mom.document.querySelectorAll('[data-testid="' + id + '"]')
                    .forEach(function (e) {{ list.push(e); }});
            }});
        return list;
    }}
    function smoothTop() {{
        var moved = false;
        cands().forEach(function (el) {{
            if (el && el.scrollTop > 0 && !moved) {{ el.scrollTo({{ top: 0, behavior: "smooth" }}); moved = true; }}
        }});
        if (!moved) mom.scrollTo({{ top: 0, behavior: "smooth" }});
    }}
    if (!mom.NC_TOP_HOOK) {{
        mom.NC_TOP_HOOK = true;
        mom.document.addEventListener("click", function (event) {{
            var t = event.target;
            if (t && t.closest && t.closest("#return-to-top")) {{
                event.preventDefault();
                smoothTop();
            }}
        }});
    }}
    if (parseInt("{force_top}", 10) || !mom.NC_TOP_DONE) {{
        mom.NC_TOP_DONE = true;
        cands().forEach(function (el) {{ if (el && el.scrollTop > 0) el.scrollTop = 0; }});
    }}
}})();
</script>
""",
        height=0,
    )


# ---------------------------------------------------------------------------
# Historial global
# ---------------------------------------------------------------------------
def render_history_tab() -> None:
    st.subheader("📜 Historial de actividad")
    rows = service.event_stream()
    if not rows:
        st.info("Aún no hay actividad registrada.")
        return
    for ts, job, ev in rows[:200]:
        fecha = (ts or "")[:16].replace("T", " ")
        st.markdown(f"**{job.client}** · {fecha} · _{ev.get('evento')}_")
        st.caption(f"– {ev.get('detalle')}")
        st.divider()


# ---------------------------------------------------------------------------
# Recordatorios (próximos / vencidos) en tarjetas navegables
# ---------------------------------------------------------------------------
def render_reminders_tab() -> None:
    st.subheader("🔔 Recordatorios")
    st.caption("Toca una tarjeta para ir directo al trabajo.")

    upcoming, overdue_list = service.reminders()
    if not upcoming and not overdue_list:
        st.info("No hay trabajos con fechas. Fija una entrega o recordatorio al crear "
                "un trabajo o desde '⚙️ Editar'.")
        return

    _render_reminder_cards("⚠️ Vencidos", overdue_list, key_prefix="ven")
    _render_reminder_cards("📌 Próximos (30 días)", upcoming, key_prefix="prox")


def _render_reminder_cards(title: str, items, key_prefix: str) -> None:
    st.markdown(f"#### {title}")
    if not items:
        st.caption("Ninguno.")
        return
    for job, d in items[:20]:
        with st.container(border=True):
            head_l, head_r = st.columns([3, 2])
            with head_l:
                st.markdown(job_badges(job), unsafe_allow_html=True)
                st.markdown(
                    f'<div class="alert-card-title">{job.client}</div>',
                    unsafe_allow_html=True,
                )
            with head_r:
                st.markdown(
                    f'<div class="alert-card-date">🗓 {d.isoformat()}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="alert-card-total">{money(job.subtotal())}</div>',
                    unsafe_allow_html=True,
                )
            meta = f"Creado: {_fecha(job.created_at)}"
            if job.notes:
                meta += " · 📝 notas"
            st.markdown(f'<div class="job-meta">{meta}</div>', unsafe_allow_html=True)
            if st.button("Ir al trabajo →", key=f"{key_prefix}_go_{job.id}",
                         use_container_width=True):
                st.session_state["_go_page"] = "Tablero"
                st.session_state["_focus_job"] = job.id
                st.rerun()


# ---------------------------------------------------------------------------
# Bloc de notas
# ---------------------------------------------------------------------------
def render_notes_tab() -> None:
    st.subheader("🏷️ Bloc de notas")
    st.caption("Guarda aquí tus pasos y código reutilizables y enlázalos a trabajos.")

    with st.expander("➕ Nueva nota o importar", expanded=False):
        mode = st.radio("Origen", ["Pegar/texto", "Archivo .txt"], horizontal=True, key="nota_modo")
        content = None
        if mode == "Archivo .txt":
            up = st.file_uploader("Selecciona el .txt", type=["txt"], key="nota_file")
            if up is not None:
                content = up.read().decode("utf-8", errors="replace")
        else:
            content = st.text_area("Contenido (pasos y código)", height=180, key="nota_paste")
        title = st.text_input("Título de la nota (opcional)", key="nota_title")
        preview_btn = st.button("👁️ Vista previa", key="nota_preview")
        save_btn = st.button("💾 Guardar como nota", type="primary", key="nota_save")

        if preview_btn and content and content.strip():
            st.session_state["_nota_preview"] = content
        preview = st.session_state.get("_nota_preview")
        if content and content.strip() and (preview_btn or preview == content):
            she = count_sections(content)
            st.caption(f"Secciones detectadas: {she}")
            _render_nota_blocks(content)
        if save_btn and content and content.strip():
            try:
                t = (title or "").strip() or "Nota importada"
                service.create_note(t, content)
                st.session_state.pop("_nota_preview", None)
                st.toast("Nota guardada.")
                st.rerun()
            except JobError as exc:
                st.error(str(exc))

    search = st.text_input("Buscar en el bloc", key="nota_buscar", placeholder="Título o contenido…")
    for note in service.list_notes(search or None):
        with st.expander(f"{note.title} · {len(note.linked_job_ids)} enlace(s) · {note.updated_at[:10]}", expanded=False):
            _render_nota_blocks(note.content)
            c1, c2, c3 = st.columns(3)
            if c1.button("✏️ Editar", key=f"nedit_{note.id}"):
                st.session_state["_edit_note"] = note.id
                st.rerun()
            if c2.button("🔗 Enlazar a trabajo", key=f"nlink_{note.id}"):
                st.session_state["_link_note"] = note.id
                st.rerun()
            if c3.button("🗑 Eliminar", key=f"ndel_{note.id}"):
                service.delete_note(note.id)
                st.toast("Nota eliminada.")
                st.rerun()

            if st.session_state.get("_edit_note") == note.id:
                with st.form(f"ednota_{note.id}"):
                    t = st.text_input("Título", value=note.title)
                    c = st.text_area("Contenido", value=note.content, height=180)
                    if st.form_submit_button("💾 Guardar nota"):
                        try:
                            service.update_note(note.id, t, c)
                            st.session_state.pop("_edit_note", None)
                            st.toast("Nota actualizada.")
                            st.rerun()
                        except JobError as exc:
                            st.error(str(exc))

            if st.session_state.get("_link_note") == note.id:
                jobs = service.list_jobs()
                opts = {f"{j.client} · {j.state}": j.id for j in jobs}
                if not opts:
                    st.caption("No hay trabajos para enlazar.")
                else:
                    choice = st.selectbox("Trabajo", list(opts), key=f"lnk_sel_{note.id}")
                    if st.button("Enlazar", key=f"lnk_ok_{note.id}"):
                        try:
                            service.link_note(opts[choice], note.id)
                            st.session_state.pop("_link_note", None)
                            st.toast("Nota enlazada al trabajo.")
                            st.rerun()
                        except JobError as exc:
                            st.error(str(exc))
                if st.button("Cerrar", key=f"lnk_x_{note.id}"):
                    st.session_state.pop("_link_note", None)
                    st.rerun()

            if note.linked_job_ids:
                st.caption("Enlazada a trabajos:")
                for jid in note.linked_job_ids:
                    try:
                        job = service.get_job(jid)
                        st.markdown(f"- {job.client} · {job.state}")
                    except JobError:
                        continue


# ---------------------------------------------------------------------------
# Respaldo / exportación
# ---------------------------------------------------------------------------
def render_backup_panel() -> None:
    st.subheader("📦 Respaldo y exportación")
    if isinstance(service.repo, GithubRepository):
        st.caption(
            "🟢 Respaldo duradero activo: los datos se guardan de forma "
            "automática en tu repositorio privado de GitHub y sobreviven a "
            "reinicios del servidor."
        )
    else:
        st.caption(
            "🟠 Almacenamiento local temporal: los datos se guardan en este "
            "servidor y pueden perderse al reiniciarse. Configura el token de "
            "GitHub en los Secrets de la app (sección [github]) para "
            "persistirlos."
        )
    st.markdown(
        "Tus datos viven en la nube, en un archivo propio por usuario: "
        "sobreviven a la pérdida o deterioro del teléfono. "
        "Usa las descargas para copiarlos o llevarlos a otro lugar."
    )
    st.divider()
    st.subheader("⬇️ Exportar datos")
    try:
        doc = service.repo.load_document()
        json_payload = json.dumps(doc, ensure_ascii=False, indent=2).encode("utf-8")
    except Exception:
        json_payload = b"{}"
    c1, c2 = st.columns(2)
    c1.download_button(
        "💾 Copia universal (JSON)",
        data=json_payload,
        file_name="registro_trabajos.json",
        mime="application/json",
    )
    csv_bytes = service.export_csv_text().encode("utf-8-sig")
    c2.download_button(
        "📊 Exportar CSV (Excel/Sheets)",
        data=csv_bytes,
        file_name="trabajos.csv",
        mime="text/csv",
    )
    st.caption("JSON: copia completa del documento (universal). CSV: formato de hoja de cálculo.")