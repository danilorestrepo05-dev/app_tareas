"""Modelos de dominio y máquina de estados del registro de trabajos.

La lógica de negocio vive aquí y en ``services``; nunca conoce la capa física
(JSON local / Drive), que queda encapsulada en ``repositories``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, List, Optional

SCHEMA_VERSION = 2

# --------------------------------------------------------------------------
# Estados del flujo (orden estricto, sin saltos)
# --------------------------------------------------------------------------
STATE_PENDIENTE = "Pendiente"
STATE_EN_PROGRESO = "En Progreso"
STATE_COMPLETADO = "Completado (Local)"
STATE_EN_PRODUCCION = "En Producción"
STATE_REALIZADO_PAGADO = "Realizado y Pagado"

STATE_LABELS: tuple[str, ...] = (
    STATE_PENDIENTE,
    STATE_EN_PROGRESO,
    STATE_COMPLETADO,
    STATE_EN_PRODUCCION,
    STATE_REALIZADO_PAGADO,
)

#: Transiciones permitidas. El flujo es estricto: no se pueden saltar etapas.
ALLOWED_TRANSITIONS: dict[str, tuple[str, ...]] = {
    STATE_PENDIENTE: (STATE_EN_PROGRESO,),
    STATE_EN_PROGRESO: (STATE_COMPLETADO,),
    STATE_COMPLETADO: (STATE_EN_PRODUCCION,),
    STATE_EN_PRODUCCION: (STATE_REALIZADO_PAGADO,),
    STATE_REALIZADO_PAGADO: (),
}

STATE_ORDER: dict[str, int] = {label: i for i, label in enumerate(STATE_LABELS)}

#: A partir de "Completado (Local)" el costo y las horas quedan congelados.
LOCKED_FROM: frozenset[str] = frozenset(
    (STATE_COMPLETADO, STATE_EN_PRODUCCION, STATE_REALIZADO_PAGADO)
)

# --------------------------------------------------------------------------
# Tipos de trabajo
# --------------------------------------------------------------------------
TYPE_POR_HORA = "Por Hora"
TYPE_POR_SERVICIO = "Por Servicio"
JOB_TYPES: tuple[str, ...] = (TYPE_POR_HORA, TYPE_POR_SERVICIO)


def now_iso() -> str:
    """Timestamp UTC en ISO-8601 (segundos)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def iso_today() -> str:
    return date.today().isoformat()


def _to_float(value: Any) -> float:
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def _opt_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return _to_float(value)


def _opt_date(value: Any) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)


def _opt_str(value: Any) -> str:
    return str(value or "")


def _str_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _hist_list(value: Any) -> List[dict]:
    if isinstance(value, list):
        return [v for v in value if isinstance(v, dict)]
    return []


def make_event(evento: str, detalle: str) -> dict:
    return {"ts": now_iso(), "evento": evento, "detalle": detalle}


@dataclass
class Job:
    """Registro de un trabajo freelance (Por Hora o Por Servicio)."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    client: str = ""
    job_type: str = TYPE_POR_HORA
    state: str = STATE_PENDIENTE
    hourly_rate: float = 0.0
    hours_invested: float = 0.0
    fixed_price: float = 0.0
    frozen_subtotal: Optional[float] = None
    created_at: str = field(default_factory=now_iso)
    estimated_delivery: Optional[str] = None
    reminder_date: Optional[str] = None
    completed_at: Optional[str] = None
    paid_at: Optional[str] = None
    notes: str = ""
    note_ids: List[str] = field(default_factory=list)
    history: List[dict] = field(default_factory=list)

    # -- Cálculo de costo --------------------------------------------------
    def subtotal(self) -> float:
        """Subtotal del trabajo.

        Si el contador quedó congelado (Completado en adelante) devuelve el
        valor congelado; en vivo, calcula según ``job_type``.
        """
        if self.frozen_subtotal is not None:
            return round(self.frozen_subtotal, 2)
        if self.job_type == TYPE_POR_HORA:
            return round(max(self.hourly_rate, 0.0) * max(self.hours_invested, 0.0), 2)
        return round(max(self.fixed_price, 0.0), 2)

    @property
    def inverted_hours(self) -> float:
        return max(self.hours_invested, 0.0)

    @property
    def is_editable(self) -> bool:
        """Los campos económicos ya no se pueden tocar a partir de Completado."""
        return self.state not in LOCKED_FROM

    @property
    def is_done(self) -> bool:
        return self.state == STATE_REALIZADO_PAGADO

    def possible_states(self) -> list[str]:
        return list(ALLOWED_TRANSITIONS.get(self.state, ()))

    # -- Serialización -----------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "client": self.client,
            "job_type": self.job_type,
            "state": self.state,
            "hourly_rate": round(self.hourly_rate, 2),
            "hours_invested": round(self.hours_invested, 2),
            "fixed_price": round(self.fixed_price, 2),
            "frozen_subtotal": self.frozen_subtotal,
            "created_at": self.created_at,
            "estimated_delivery": self.estimated_delivery,
            "reminder_date": self.reminder_date,
            "completed_at": self.completed_at,
            "paid_at": self.paid_at,
            "notes": self.notes,
            "note_ids": list(self.note_ids),
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Job":
        state = data.get("state")
        if state not in STATE_LABELS:
            state = STATE_PENDIENTE
        job_type = data.get("job_type")
        if job_type not in JOB_TYPES:
            job_type = TYPE_POR_HORA
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            client=str(data.get("client") or "").strip(),
            job_type=job_type,
            state=state,
            hourly_rate=_to_float(data.get("hourly_rate")),
            hours_invested=_to_float(data.get("hours_invested")),
            fixed_price=_to_float(data.get("fixed_price")),
            frozen_subtotal=_opt_float(data.get("frozen_subtotal")),
            created_at=str(data.get("created_at") or now_iso()),
            estimated_delivery=_opt_date(data.get("estimated_delivery")),
            reminder_date=_opt_date(data.get("reminder_date")),
            completed_at=_opt_date(data.get("completed_at")),
            paid_at=_opt_date(data.get("paid_at")),
            notes=_opt_str(data.get("notes")),
            note_ids=_str_list(data.get("note_ids")),
            history=_hist_list(data.get("history")),
        )

    @classmethod
    def sort_key(cls, job: "Job") -> tuple[int, str]:
        """Orden: estado (pendiente primero) y luego creación (más reciente)."""
        return (STATE_ORDER.get(job.state, len(STATE_ORDER)), _sort_ts(job.created_at))


@dataclass
class Note:
    """Nota del bloc global, enlazable a uno o varios trabajos."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    title: str = ""
    content: str = ""
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    linked_job_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "linked_job_ids": list(self.linked_job_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Note":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            title=_opt_str(data.get("title")).strip(),
            content=_opt_str(data.get("content")),
            created_at=str(data.get("created_at") or now_iso()),
            updated_at=str(data.get("updated_at") or now_iso()),
            linked_job_ids=_str_list(data.get("linked_job_ids")),
        )


def _sort_ts(value: str) -> str:
    """Normaliza el timestamp para ordenar cadena a cadena."""
    return str(value or "").replace(" ", "T")