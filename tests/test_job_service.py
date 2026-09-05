"""Pruebas de la máquina de estados, persistencia, agrupación, historial,
recordatorios, bloc de notas, parser y exportación (sin UI ni Streamlit)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from core.models import (
    STATE_COMPLETADO,
    STATE_EN_PRODUCCION,
    STATE_EN_PROGRESO,
    STATE_PENDIENTE,
    STATE_REALIZADO_PAGADO,
    TYPE_POR_HORA,
    TYPE_POR_SERVICIO,
    Job,
    now_iso,
)
from repositories.local_json import LocalJsonRepository
from services.job_service import JobError, JobService
from services.parser_notas import count_sections, parse


@pytest.fixture
def service(tmp_path):
    """Servicio aislado con archivo local temporal."""
    repo = LocalJsonRepository(str(tmp_path / "data" / "trabajos.json"))
    return JobService(repo)


# ---------------------------------------------------------------------------
# Reglas de negocio: estados y costo
# ---------------------------------------------------------------------------
def test_create_hour_job_computes_subtotal_in_live(service):
    job = service.create_job("Cliente A", TYPE_POR_HORA, hourly_rate=25, hours_invested=4)
    assert job.subtotal() == 100.0
    assert job.state == STATE_PENDIENTE


def test_create_service_job_ignores_rate(service):
    job = service.create_job("Cliente B", TYPE_POR_SERVICIO, hourly_rate=999, fixed_price=500)
    assert job.job_type == TYPE_POR_SERVICIO
    assert job.hourly_rate == 0.0
    assert job.subtotal() == 500.0


def test_strict_transitions_reject_skips(service):
    job = service.create_job("Cliente C", TYPE_POR_SERVICIO, fixed_price=100)
    with pytest.raises(JobError):
        service.advance(job.id, STATE_COMPLETADO)  # Pendiente -> Completado: prohibido
    assert service.get_job(job.id).state == STATE_PENDIENTE


def test_full_forward_flow_and_freeze_on_completed(service):
    job = service.create_job("Cliente D", TYPE_POR_HORA, hourly_rate=50, hours_invested=3)
    service.advance(job.id, STATE_EN_PROGRESO)
    service.add_hours(job.id, 2)  # ahora 5 h, subtotal vivo 250
    assert service.get_job(job.id).subtotal() == 250.0

    service.advance(job.id, STATE_COMPLETADO)
    job = service.get_job(job.id)
    assert job.frozen_subtotal == 250.0
    assert job.completed_at

    # Congelado: no se pueden sumar horas ni cambiar precio.
    with pytest.raises(JobError):
        service.add_hours(job.id, 1)
    with pytest.raises(JobError):
        service.update_details(job.id, hourly_rate=99)

    service.advance(job.id, STATE_EN_PRODUCCION)
    service.advance(job.id, STATE_REALIZADO_PAGADO)
    job = service.get_job(job.id)
    assert job.paid_at
    assert job.subtotal() == 250.0  # el subtotal congelado no cambia


def test_update_notes_allowed_when_frozen(service):
    job = service.create_job("Cliente N", TYPE_POR_HORA, hourly_rate=10, hours_invested=1)
    service.advance(job.id, STATE_EN_PROGRESO)
    service.advance(job.id, STATE_COMPLETADO)
    job = service.update_notes(job.id, "Pasos: instalar módulo x")
    assert job.notes.startswith("Pasos")
    assert job.subtotal() == 10.0  # el costo sigue congelado


def test_prev_state_disallows_from_pending_and_done():
    assert Job(state=STATE_EN_PROGRESO).prev_state() == STATE_PENDIENTE
    assert Job(state=STATE_COMPLETADO).prev_state() == STATE_EN_PROGRESO
    assert Job(state=STATE_EN_PRODUCCION).prev_state() == STATE_COMPLETADO
    assert Job(state=STATE_PENDIENTE).prev_state() is None
    assert Job(state=STATE_REALIZADO_PAGADO).prev_state() is None


def test_regress_goes_one_step_back_and_unfreezes(service):
    job = service.create_job("Cliente R1", TYPE_POR_HORA, hourly_rate=10, hours_invested=2)
    service.advance(job.id, STATE_EN_PROGRESO)
    service.advance(job.id, STATE_COMPLETADO)
    job = service.get_job(job.id)
    assert job.frozen_subtotal == 20.0

    job = service.regress(job.id)
    assert job.state == STATE_EN_PROGRESO
    assert job.frozen_subtotal is None
    assert job.completed_at is None
    assert job.subtotal() == 20.0  # vivo otra vez: se pueden sumar horas

    service.add_hours(job.id, 1)
    assert service.get_job(job.id).subtotal() == 30.0


def test_regress_from_en_produccion_back_to_completado_keeps_frozen(service):
    job = service.create_job("Cliente R4", TYPE_POR_HORA, hourly_rate=10, hours_invested=2)
    service.advance(job.id, STATE_EN_PROGRESO)
    service.advance(job.id, STATE_COMPLETADO)
    service.advance(job.id, STATE_EN_PRODUCCION)

    job = service.regress(job.id)
    assert job.state == STATE_COMPLETADO
    assert job.frozen_subtotal == 20.0  # sigue congelado: solo se deshace al volver a En Progreso


def test_regress_forbidden_from_done_and_pending(service):
    job = service.create_job("Cliente R2", TYPE_POR_SERVICIO, fixed_price=100)
    service.advance(job.id, STATE_EN_PROGRESO)
    service.advance(job.id, STATE_COMPLETADO)
    service.advance(job.id, STATE_EN_PRODUCCION)
    service.advance(job.id, STATE_REALIZADO_PAGADO)
    with pytest.raises(JobError):
        service.regress(job.id)
    assert service.get_job(job.id).state == STATE_REALIZADO_PAGADO

    job2 = service.create_job("Cliente R3", TYPE_POR_SERVICIO, fixed_price=50)
    with pytest.raises(JobError):
        service.regress(job2.id)
    assert service.get_job(job2.id).state == STATE_PENDIENTE


def test_regress_records_history_event(service):
    job = service.create_job("Cliente R5", TYPE_POR_SERVICIO, fixed_price=100)
    service.advance(job.id, STATE_EN_PROGRESO)
    service.advance(job.id, STATE_COMPLETADO)
    service.regress(job.id)
    row = service.get_job(job.id)
    assert row.history[-1]["evento"] == "estado"
    assert "← En Progreso" in row.history[-1]["detalle"]


def test_stats_money_pending_until_realizado(service):
    # Pendiente, Completado (Local) y En Producción: todo cuenta como "pendiente".
    service.create_job("Cliente P1", TYPE_POR_SERVICIO, fixed_price=100)
    job = service.create_job("Cliente P2", TYPE_POR_HORA, hourly_rate=50, hours_invested=2)
    service.advance(job.id, STATE_EN_PROGRESO)
    service.advance(job.id, STATE_COMPLETADO)  # 100 congelados
    job3 = service.create_job("Cliente P3", TYPE_POR_SERVICIO, fixed_price=200)
    service.advance(job3.id, STATE_EN_PROGRESO)
    service.advance(job3.id, STATE_COMPLETADO)
    service.advance(job3.id, STATE_EN_PRODUCCION)  # en producción: pendiente aún
    billed = service.create_job("Cliente P4", TYPE_POR_SERVICIO, fixed_price=500)
    service.advance(billed.id, STATE_EN_PROGRESO)
    service.advance(billed.id, STATE_COMPLETADO)
    service.advance(billed.id, STATE_EN_PRODUCCION)
    service.advance(billed.id, STATE_REALIZADO_PAGADO)

    stats = service.stats()
    assert stats["total_billed"] == 500.0  # solo "Realizado y Pagado"
    assert stats["total_pending"] == 400.0  # 100 + 100 + 200
    assert stats["counts"][STATE_EN_PRODUCCION] == 1


def test_create_job_with_backdated_creation(service):
    job = service.create_job(
        "Cliente Fecha", TYPE_POR_SERVICIO, fixed_price=80, created_at="2024-03-01"
    )
    assert job.created_at[:10] == "2024-03-01"
    reloaded = JobService(service.repo)
    assert reloaded.get_job(job.id).created_at[:10] == "2024-03-01"


def test_create_job_defaults_creation_date_to_now(service):
    job = service.create_job("Cliente Auto", TYPE_POR_SERVICIO, fixed_price=80)
    assert job.created_at[:10] == now_iso()[:10]


def test_persist_roundtrip_and_shadow_write(tmp_path):
    path = tmp_path / "data" / "trabajos.json"
    repo = LocalJsonRepository(str(path))
    service = JobService(repo)
    service.create_job("Cliente R", TYPE_POR_SERVICIO, fixed_price=120)

    # Segunda instancia lee lo persistido.
    repo2 = LocalJsonRepository(str(path))
    service2 = JobService(repo2)
    assert len(service2.list_jobs()) == 1
    assert service2.list_jobs()[0].client == "Cliente R"

    # No debe quedar archivo temporal huérfano tras guardar.
    import pathlib

    leftovers = list(pathlib.Path(path).parent.glob("*.tmp"))
    assert leftovers == []


def test_migration_from_v1_plain_list(tmp_path):
    path = tmp_path / "data" / "trabajos.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '[{"id": "x1", "client": "Cliente V1", "job_type": "Por Servicio", '
        '"fixed_price": 300}]',
        encoding="utf-8",
    )
    repo = LocalJsonRepository(str(path))
    doc = repo.load_document()
    assert doc["schema_version"] == 2
    assert len(doc["jobs"]) == 1
    service = JobService(repo)
    assert service.list_jobs()[0].client == "Cliente V1"
    assert service.list_notes() == []


# ---------------------------------------------------------------------------
# Agrupación, historial y recordatorios
# ---------------------------------------------------------------------------
def test_group_by_client_lowercase_and_order(service):
    service.create_job("Agencia Uno", TYPE_POR_SERVICIO, fixed_price=100)
    service.create_job("  agencia uno  ", TYPE_POR_HORA, hourly_rate=5, hours_invested=2)
    service.create_job("Cliente X", TYPE_POR_SERVICIO, fixed_price=50)

    groups = service.group_by_client()
    assert len(groups) == 2
    names = {g.lower() for g, _ in groups}
    assert {"agencia uno", "cliente x"} == names
    agencia_members = [ms for g, ms in groups if g.lower() == "agencia uno"]
    assert len(agencia_members[0]) == 2


def test_history_records_events(service):
    job = service.create_job("Cliente H", TYPE_POR_SERVICIO, fixed_price=200)
    events = service.event_stream()
    assert any(ev.get("evento") == "creado" for _, _, ev in events)
    row = service.get_job(job.id)
    assert row.history[0]["evento"] == "creado"


def test_reminders_and_delivery_markers(service):
    hoy = date.today()
    pasado = (hoy - timedelta(days=3)).isoformat()
    futuro = (hoy + timedelta(days=5)).isoformat()
    lejano = (hoy + timedelta(days=120)).isoformat()

    service.create_job("Vencido", TYPE_POR_SERVICIO, reminder_date=pasado, fixed_price=10)
    service.create_job("Próximo", TYPE_POR_SERVICIO, reminder_date=futuro, fixed_price=10)
    service.create_job("Lejano", TYPE_POR_SERVICIO, reminder_date=lejano, fixed_price=10)
    service.create_job("Entregado", TYPE_POR_SERVICIO, estimated_delivery=pasado, fixed_price=10)

    upcoming, overdue = service.reminders()
    # "Entregado" cuenta como vencido por su fecha de entrega (sin recordatorio).
    assert [c.client for c, _ in overdue] == ["Vencido", "Entregado"]
    assert [c.client for c, _ in upcoming] == ["Próximo"]

    markers = service.delivery_markers(hoy.year, hoy.month)
    assert isinstance(markers, dict)


def test_notes_crud_and_linking(service):
    job = service.create_job("Cliente L", TYPE_POR_SERVICIO, fixed_price=90)
    note = service.create_note("Configurar Odoo", "***Pasos***\n1. Crear el módulo\n")
    assert service.list_notes()[0].title == "Configurar Odoo"

    service.link_note(job.id, note.id)
    job2 = service.get_job(job.id)
    assert note.id in job2.note_ids
    assert service.get_note(note.id).linked_job_ids == [job.id]

    service.unlink_note(job.id, note.id)
    assert service.get_job(job.id).note_ids == []

    service.delete_note(note.id)
    with pytest.raises(JobError):
        service.get_note(note.id)


def test_csv_export_includes_header_and_rows(service):
    service.create_job("Cliente CSV", TYPE_POR_HORA, hourly_rate=10, hours_invested=3)
    text = service.export_csv_text()
    assert "cliente_empresa" in text
    assert "Cliente CSV" in text
    assert "30.00" in text


# ---------------------------------------------------------------------------
# Parser de notas
# ---------------------------------------------------------------------------
def test_parser_detects_titles_steps_and_code():
    text = (
        "# Configurar módulo\n"
        "***Instalación***\n"
        "Ajustes → Apps, buscar el módulo\n"
        "Guardar y reiniciar\n"
        '<record id="x" model="res.partner"/>\n'
    )
    blocks = parse(text)
    tipos = [b["tipo"] for b in blocks]
    assert "titulo" in tipos
    assert "pasos" in tipos
    assert "codigo" in tipos
    assert count_sections(text) >= 1


def test_parser_keeps_lines_together():
    text = "# Titulo\nLínea simple"
    blocks = parse(text)
    assert blocks[0]["tipo"] == "titulo"
    assert blocks[1]["tipo"] == "texto"