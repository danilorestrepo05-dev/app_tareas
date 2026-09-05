"""Capa de aplicación: valida transiciones de estado y reglas de costo,
gestiona el historial, el bloc de notas global, la agrupación por empresa,
los recordatorios y la exportación CSV.

La capa solo conoce ``BaseRepository``; no importa JSON real, ni Drive, ni
archivos. Toda escritura sale por aquí a través del repositorio.
"""

from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from typing import List, Optional, Tuple

from core.models import (
    JOB_TYPES,
    SCHEMA_VERSION,
    STATE_COMPLETADO,
    STATE_EN_PROGRESO,
    STATE_ORDER,
    STATE_PENDIENTE,
    STATE_REALIZADO_PAGADO,
    TYPE_POR_HORA,
    TYPE_POR_SERVICIO,
    Job,
    Note,
    make_event,
    now_iso,
)
from repositories.base import BaseRepository

DEFAULT_REMINDER_WINDOW_DAYS = 30


class JobError(ValueError):
    """Error de regla de negocio con mensaje amigable."""


class JobService:
    def __init__(self, repo: BaseRepository) -> None:
        self.repo = repo
        self._jobs: dict[str, Job] = {}
        self._notes: dict[str, Note] = {}
        doc = repo.load_document()
        for raw in doc.get("jobs", []):
            if isinstance(raw, dict):
                job = Job.from_dict(raw)
                self._jobs[job.id] = job
        for raw in doc.get("notes", []):
            if isinstance(raw, dict):
                note = Note.from_dict(raw)
                self._notes[note.id] = note

    # -- Persistencia interna ----------------------------------------------
    def _document(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "jobs": [j.to_dict() for j in self._jobs.values()],
            "notes": [n.to_dict() for n in self._notes.values()],
        }

    def _persist(self) -> None:
        self.repo.save_document(self._document())

    def sync_mirror(self) -> Optional[str]:
        """Fuerza push al respaldo (Drive). Devuelve el error si lo hay."""
        self._persist()
        return getattr(self.repo, "last_error", None)

    # -- Trabajos: consultas -------------------------------------------------
    def list_jobs(
        self, state: Optional[str] = None, job_type: Optional[str] = None
    ) -> List[Job]:
        jobs = list(self._jobs.values())
        if state:
            jobs = [j for j in jobs if j.state == state]
        if job_type:
            jobs = [j for j in jobs if j.job_type == job_type]
        jobs.sort(key=Job.sort_key)
        return jobs

    def get_job(self, job_id: str) -> Job:
        try:
            return self._jobs[job_id]
        except KeyError:
            raise JobError("El trabajo no existe (¿fue eliminado?).") from None

    def stats(self) -> dict:
        """Resumen monetario: el precio es "pendiente" hasta que el trabajo
        esté en 'Realizado y Pagado'; solo entonces pasa a "facturado"."""
        total_billed = 0.0
        total_pending = 0.0
        counts = {s: 0 for s in STATE_ORDER}
        active = 0
        for j in self._jobs.values():
            counts[j.state] = counts.get(j.state, 0) + 1
            if j.state == STATE_REALIZADO_PAGADO:
                total_billed += j.subtotal()
            else:
                total_pending += j.subtotal()
            if j.state in (STATE_PENDIENTE, STATE_EN_PROGRESO):
                active += 1
        return {
            "total": len(self._jobs),
            "active": active,
            "counts": counts,
            "total_billed": round(total_billed, 2),
            "total_pending": round(total_pending, 2),
        }

    def group_by_client(self, jobs: Optional[List[Job]] = None) -> List[Tuple[str, List[Job]]]:
        """Agrupa trabajos por cliente/empresa; grupos ordenados por actividad
        más reciente y, dentro de cada grupo, trabajos recientes primero."""
        source = jobs if jobs is not None else self.list_jobs()
        buckets: dict[str, List[Job]] = {}
        for j in source:
            key = (j.client or "").strip().lower()
            buckets.setdefault(key, []).append(j)
        groups: List[Tuple[str, List[Job]]] = []
        for key, members in buckets.items():
            members.sort(key=lambda j: j.created_at, reverse=True)
            display = members[0].client.strip() or "Sin cliente"
            groups.append((display, members))
        groups.sort(key=lambda g: g[1][0].created_at, reverse=True)
        return groups

    # -- Trabajos: escritura ---------------------------------------------------
    def create_job(
        self,
        client: str,
        job_type: str,
        hourly_rate: float = 0.0,
        hours_invested: float = 0.0,
        fixed_price: float = 0.0,
        estimated_delivery: Optional[str] = None,
        reminder_date: Optional[str] = None,
        notes: str = "",
        created_at: Optional[str] = None,
    ) -> Job:
        if not client or not client.strip():
            raise JobError("Indica el cliente o la empresa.")
        if job_type not in JOB_TYPES:
            raise JobError("Tipo de trabajo inválido.")
        if job_type == TYPE_POR_SERVICIO:
            hourly_rate, hours_invested = 0.0, 0.0
        else:
            fixed_price = 0.0
            if hourly_rate < 0 or hours_invested < 0:
                raise JobError("La tarifa y las horas no pueden ser negativas.")
        job = Job(
            client=client.strip(),
            job_type=job_type,
            hourly_rate=round(max(hourly_rate, 0.0), 2),
            hours_invested=round(max(hours_invested, 0.0), 2),
            fixed_price=round(max(fixed_price, 0.0), 2),
            estimated_delivery=estimated_delivery,
            reminder_date=reminder_date,
            notes=notes or "",
            created_at=created_at or now_iso(),
        )
        job.history.append(make_event("creado", "Trabajo creado."))
        self._jobs[job.id] = job
        self._persist()
        return job

    def update_details(
        self,
        job_id: str,
        client: Optional[str] = None,
        hourly_rate: Optional[float] = None,
        hours_invested: Optional[float] = None,
        fixed_price: Optional[float] = None,
        estimated_delivery: Optional[str] = None,
        reminder_date: Optional[str] = None,
        created_at: Optional[str] = None,
    ) -> Job:
        job = self.get_job(job_id)
        if not job.is_editable:
            raise JobError("A partir de 'Completado (Local)' los datos quedan congelados.")
        changed: List[str] = []
        if created_at is not None:
            c = created_at or None
            if c != job.created_at:
                job.created_at = c
                changed.append("fecha de inicio")
        if client is not None:
            if not str(client).strip():
                raise JobError("El cliente no puede quedar vacío.")
            c = str(client).strip()
            if c != job.client:
                job.client = c
                changed.append("cliente")
        if job.job_type == TYPE_POR_HORA:
            if hourly_rate is not None and float(hourly_rate) != job.hourly_rate:
                if float(hourly_rate) < 0:
                    raise JobError("La tarifa no puede ser negativa.")
                job.hourly_rate = round(float(hourly_rate), 2)
                changed.append("tarifa")
            if hours_invested is not None and float(hours_invested) != job.hours_invested:
                if float(hours_invested) < 0:
                    raise JobError("Las horas no pueden ser negativas.")
                job.hours_invested = round(float(hours_invested), 2)
                changed.append("horas")
        else:
            if fixed_price is not None and float(fixed_price) != job.fixed_price:
                if float(fixed_price) < 0:
                    raise JobError("El precio no puede ser negativo.")
                job.fixed_price = round(float(fixed_price), 2)
                changed.append("precio")
        job.estimated_delivery = estimated_delivery
        job.reminder_date = reminder_date
        job.history.append(
            make_event("editado", "Datos actualizados" + (": " + ", ".join(changed) if changed else "."))
        )
        self._persist()
        return job

    def update_notes(self, job_id: str, notes: str) -> Job:
        """Las notas son informativas: editables en cualquier estado."""
        job = self.get_job(job_id)
        if (notes or "") != (job.notes or ""):
            job.notes = notes or ""
            job.history.append(make_event("notas", "Notas actualizadas."))
            self._persist()
        return job

    def set_job_dates(
        self, job_id: str, estimated_delivery: Optional[str], reminder_date: Optional[str]
    ) -> Job:
        job = self.get_job(job_id)
        job.estimated_delivery = estimated_delivery
        job.reminder_date = reminder_date
        self._persist()
        return job

    def add_hours(self, job_id: str, hours: float) -> Job:
        job = self.get_job(job_id)
        if job.job_type != TYPE_POR_HORA:
            raise JobError("Solo los trabajos 'Por Hora' acumulan horas.")
        if not job.is_editable:
            raise JobError("El contador de horas quedó congelado (trabajo Completado).")
        if hours <= 0:
            raise JobError("Suma un valor de horas mayor que cero.")
        job.hours_invested = round(job.hours_invested + float(hours), 2)
        job.history.append(
            make_event("horas", f"+{float(hours):g} h (total {job.inverted_hours:g} h).")
        )
        self._persist()
        return job

    def advance(self, job_id: str, target: str) -> Job:
        """Transición de estado estricta: valida contra ALLOWED_TRANSITIONS."""
        job = self.get_job(job_id)
        allowed = job.possible_states()
        if target not in allowed:
            raise JobError(
                f"No se puede ir de '{job.state}' a '{target}'. "
                f"Opciones válidas: {', '.join(allowed) or 'ninguna'}."
            )
        previous = job.state
        if target == STATE_COMPLETADO and job.job_type == TYPE_POR_HORA:
            # Congelar contador y calcular subtotal al momento de completar.
            job.frozen_subtotal = round(
                max(job.hourly_rate, 0.0) * max(job.hours_invested, 0.0), 2
            )
        if target == STATE_COMPLETADO:
            job.completed_at = job.completed_at or now_iso()
        if target == STATE_REALIZADO_PAGADO:
            job.paid_at = job.paid_at or now_iso()
        job.state = target
        job.history.append(make_event("estado", f"{previous} → {target}."))
        self._persist()
        return job

    def regress(self, job_id: str) -> Job:
        """Vuelve un paso atrás en el flujo. Prohibido desde 'Realizado y
        Pagado' (el trabajo está cobrado) y desde 'Pendiente' (es el inicio)."""
        job = self.get_job(job_id)
        if job.is_done:
            raise JobError(
                "Un trabajo 'Realizado y Pagado' no puede retroceder: ya está cobrado."
            )
        prev_state = job.prev_state()
        if prev_state is None:
            raise JobError(f"'{job.state}' es el estado inicial: no hay a dónde volver.")
        previous = job.state
        if previous == STATE_COMPLETADO:
            # Deshacer el congelado al volver a 'En Progreso': horas editables otra vez.
            job.frozen_subtotal = None
            job.completed_at = None
        job.state = prev_state
        job.history.append(make_event("estado", f"{previous} ← {prev_state}"))
        self._persist()
        return job

    def delete_job(self, job_id: str) -> None:
        if job_id not in self._jobs:
            raise JobError("El trabajo no existe (¿fue eliminado?).")
        del self._jobs[job_id]
        for note in self._notes.values():
            if job_id in note.linked_job_ids:
                note.linked_job_ids.remove(job_id)
        self._persist()

    # -- Recordatorios / entregas ---------------------------------------------
    def reminders(self, days: int = DEFAULT_REMINDER_WINDOW_DAYS) -> Tuple[List[Tuple[Job, date]], List[Tuple[Job, date]]]:
        """Devuelve (próximos, vencidos) en el horizonte indicado.

        Usa ``reminder_date`` (o, si no hay, la entrega estimada). Excluye
        trabajos ya 'Realizado y Pagado'.
        """
        today = date.today()
        overdue: List[Tuple[Job, date]] = []
        upcoming: List[Tuple[Job, date]] = []
        horizon = today + timedelta(days=days)
        for job in self._jobs.values():
            if job.is_done:
                continue
            target = job.reminder_date or job.estimated_delivery
            if not target:
                continue
            try:
                d = date.fromisoformat(str(target)[:10])
            except ValueError:
                continue
            if d < today:
                overdue.append((job, d))
            elif d <= horizon:
                upcoming.append((job, d))
        overdue.sort(key=lambda x: x[1])
        upcoming.sort(key=lambda x: x[1])
        return upcoming, overdue

    def delivery_markers(self, year: int, month: int) -> dict[int, List[Job]]:
        """Día → trabajos cuya entrega/recordatorio cae ese mes."""
        markers: dict[int, List[Job]] = {}
        for job in self._jobs.values():
            target = job.reminder_date or job.estimated_delivery
            if not target:
                continue
            try:
                d = date.fromisoformat(str(target)[:10])
            except ValueError:
                continue
            if d.year == year and d.month == month:
                markers.setdefault(d.day, []).append(job)
        return markers

    # -- Historial --------------------------------------------------------------
    def event_stream(self) -> List[Tuple[str, Job, dict]]:
        """Todos los eventos de la app, cronológico inverso."""
        rows: List[Tuple[str, Job, dict]] = []
        for job in self._jobs.values():
            for ev in job.history:
                rows.append((ev.get("ts", ""), job, ev))
        rows.sort(key=lambda r: r[0], reverse=True)
        return rows

    # -- Bloc de notas global -----------------------------------------------------
    def list_notes(self, search: Optional[str] = None) -> List[Note]:
        notes = sorted(self._notes.values(), key=lambda n: n.updated_at, reverse=True)
        if search:
            needle = search.lower()
            notes = [
                n
                for n in notes
                if needle in n.title.lower() or needle in n.content.lower()
            ]
        return notes

    def get_note(self, note_id: str) -> Note:
        try:
            return self._notes[note_id]
        except KeyError:
            raise JobError("La nota no existe (¿fue eliminada?).") from None

    def create_note(self, title: str, content: str) -> Note:
        if not title.strip():
            raise JobError("Pon un título a la nota.")
        note = Note(title=title.strip(), content=content or "")
        self._notes[note.id] = note
        self._persist()
        return note

    def update_note(self, note_id: str, title: str, content: str) -> Note:
        note = self.get_note(note_id)
        if not title.strip():
            raise JobError("Pon un título a la nota.")
        note.title = title.strip()
        note.content = content or ""
        note.updated_at = now_iso()
        self._persist()
        return note

    def delete_note(self, note_id: str) -> None:
        if note_id not in self._notes:
            raise JobError("La nota no existe (¿fue eliminada?).")
        del self._notes[note_id]
        for job in self._jobs.values():
            if note_id in job.note_ids:
                job.note_ids.remove(note_id)
        self._persist()

    def link_note(self, job_id: str, note_id: str) -> None:
        job = self.get_job(job_id)
        note = self.get_note(note_id)
        if note_id not in job.note_ids:
            job.note_ids.append(note_id)
        if job_id not in note.linked_job_ids:
            note.linked_job_ids.append(job_id)
        self._persist()

    def unlink_note(self, job_id: str, note_id: str) -> None:
        job = self.get_job(job_id)
        note = self.get_note(note_id)
        if note_id in job.note_ids:
            job.note_ids.remove(note_id)
        if job_id in note.linked_job_ids:
            note.linked_job_ids.remove(job_id)
        self._persist()

    # -- Exportación ---------------------------------------------------------------
    def export_csv_text(self) -> str:
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(
            [
                "id",
                "cliente_empresa",
                "tipo",
                "estado",
                "tarifa_hora",
                "horas_invertidas",
                "precio_fijo",
                "subtotal",
                "fecha_creacion",
                "entrega_estimada",
                "recordatorio",
                "fecha_completado",
                "fecha_pago",
                "notas",
            ]
        )
        jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
        for j in jobs:
            writer.writerow(
                [
                    j.id,
                    j.client,
                    j.job_type,
                    j.state,
                    f"{j.hourly_rate:.2f}",
                    f"{j.inverted_hours:.2f}",
                    f"{j.fixed_price:.2f}",
                    f"{j.subtotal():.2f}",
                    j.created_at,
                    j.estimated_delivery or "",
                    j.reminder_date or "",
                    j.completed_at or "",
                    j.paid_at or "",
                    j.notes,
                ]
            )
        return buf.getvalue()