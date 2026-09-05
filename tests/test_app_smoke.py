"""Prueba de humo de la app completa vía Streamlit AppTest (sin navegador)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

REPO_ROOT = Path(__file__).resolve().parent.parent

PAGES = ["Tablero", "Nuevo", "Bloc", "Recordatorios", "Historial", "Respaldo"]


@pytest.fixture
def isolated_data(tmp_path, monkeypatch):
    """Aísla los datos de cada test para no acoplarlos entre ejecuciones."""
    monkeypatch.setenv("APP_DATA_ROOT", str(tmp_path / "data"))
    return tmp_path


def _find_text(at, label, default=None):
    for el in at.text_input:
        if getattr(el, "label", "") == label:
            return el
    return default


def _nav(at, page):
    """Cambia de página usando la navegación superior (segmented_control)."""
    sc = at.segmented_control[0]
    if sc.value != page:
        at = sc.set_value(page).run(timeout=30)
    assert not at.exception, at.exception
    return at


def _run_login():
    """Pantalla de login en modo desarrollo (sin secrets OAuth)."""
    at = AppTest.from_file(REPO_ROOT / "app.py").run(timeout=30)
    assert not at.exception, at.exception
    email_box = _find_text(at, "Email (modo desarrollo)")
    name_box = _find_text(at, "Nombre")
    assert email_box is not None and name_box is not None
    email_box.set_value("dev@local.test").run(timeout=30)
    name_box = _find_text(at, "Nombre")
    name_box.set_value("Usuario Prueba").run(timeout=30)
    entrar = [b for b in at.button if b.label == "Entrar"]
    assert entrar, "Botón 'Entrar' no encontrado"
    entrar[0].click().run(timeout=30)
    assert not at.exception, at.exception
    return at


def test_app_loads_login_and_dashboard(isolated_data):
    at = _run_login()
    marks = [m.value for m in at.markdown]
    assert any("NotesControl" in m for m in marks)
    assert any("return-to-top" in m for m in marks)
    # Logo de marca (SVG) presente en header/login y menú con iconos Material.
    assert any("<svg" in m for m in marks)
    assert list(at.segmented_control[0].options) == PAGES
    assert not at.exception, at.exception


def test_dashboard_empty_state_and_create_flow(isolated_data):
    at = _run_login()
    # Página inicial = Tablero.
    assert any("No hay trabajos" in i.value for i in at.info)

    # Formulario "Nuevo": cliente + tarifa por hora + horas (por label).
    at = _nav(at, "Nuevo")
    cliente = _find_text(at, "Cliente / Empresa *")
    assert cliente is not None, "Campo 'Cliente / Empresa *' no encontrado"
    cliente.set_value("Agencia Demo").run(timeout=30)

    tarifa = [n for n in at.number_input if n.label == "Tarifa por hora ($)"]
    horas = [n for n in at.number_input if n.label == "Horas invertidas"]
    assert tarifa and horas
    tarifa[0].set_value(20.0).run(timeout=30)
    horas[0].set_value(3.5).run(timeout=30)
    create = [b for b in at.button if "Crear trabajo" in b.label]
    assert create, "Botón 'Crear trabajo' no encontrado"
    create[0].click().run(timeout=30)
    assert not at.exception, at.exception

    # El tablero ya no está vacío.
    at = _nav(at, "Tablero")
    infos = [i.value for i in at.info]
    assert not any("No hay trabajos" in i for i in infos)


def test_fechas_directas_sin_chocar_con_otros_widgets(isolated_data):
    """Regresión: las fechas se fijan directo (sin checkboxes) y no chocan con el botón eliminar."""
    from datetime import date

    at = _run_login()
    at = _nav(at, "Nuevo")

    cliente = _find_text(at, "Cliente / Empresa *")
    cliente.set_value("Agencia Fechas").run(timeout=30)
    tarifa = [n for n in at.number_input if n.label == "Tarifa por hora ($)"][0]
    horas = [n for n in at.number_input if n.label == "Horas invertidas"][0]
    tarifa.set_value(15.0).run(timeout=30)
    horas.set_value(2.0).run(timeout=30)

    entrega = [d for d in at.date_input if d.label == "Entrega estimada"][0]
    at = entrega.set_value(date(2026, 10, 5)).run(timeout=30)
    assert not at.exception, at.exception

    crear = [b for b in at.button if "Crear trabajo" in b.label][0]
    at = crear.click().run(timeout=30)
    assert not at.exception, at.exception

    # Con la tarjeta abierta, la edición también renderiza sus date_inputs sin colisiones.
    at = _nav(at, "Tablero")
    edit_dates = [d for d in at.date_input if d.label == "Entrega estimada"]
    assert len(edit_dates) >= 1
    assert not at.exception, at.exception


def test_note_block_creates_note(isolated_data):
    at = _run_login()
    at = _nav(at, "Bloc")
    area = [a for a in at.text_area if a.label == "Contenido (pasos y código)"]
    assert area, "Área de pegado del bloc no encontrada"
    area[0].set_value("# Configurar Odoo\nAjustes → Apps").run(timeout=30)
    guardar = [b for b in at.button if b.label == "💾 Guardar como nota"]
    assert guardar
    at = guardar[0].click().run(timeout=30)
    assert not at.exception, at.exception
    assert any("Nota importada" in e.label for e in at.expander)


def test_recordatorios_navega_a_trabajo(isolated_data):
    """Las tarjetas de próximos/vencidos llevan al trabajo en el Tablero."""
    from datetime import date, timedelta

    at = _run_login()
    at = _nav(at, "Nuevo")

    cliente = _find_text(at, "Cliente / Empresa *")
    cliente.set_value("Cliente Recordatorio").run(timeout=30)
    tarifa = [n for n in at.number_input if n.label == "Tarifa por hora ($)"][0]
    horas = [n for n in at.number_input if n.label == "Horas invertidas"][0]
    tarifa.set_value(10.0).run(timeout=30)
    horas.set_value(3.0).run(timeout=30)

    record = [d for d in at.date_input if d.label == "Recordatorio"][0]
    at = record.set_value(date.today() + timedelta(days=5)).run(timeout=30)
    assert not at.exception, at.exception

    crear = [b for b in at.button if "Crear trabajo" in b.label][0]
    at = crear.click().run(timeout=30)
    assert not at.exception, at.exception

    at = _nav(at, "Recordatorios")
    assert any("Cliente Recordatorio" in m.value for m in at.markdown)
    go = [b for b in at.button if "Ir al trabajo" in b.label]
    assert go, "Botón 'Ir al trabajo' no encontrado"
    at = go[0].click().run(timeout=30)
    assert not at.exception, at.exception
    assert at.segmented_control[0].value == "Tablero"
    assert any("Cliente Recordatorio" in m.value for m in at.markdown)