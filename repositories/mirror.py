"""Repositorio espejo: primario (local) + respaldo opcional (Drive).

- ``load_document``: lee del primario; si está vacío y hay espejo, tira del
  Drive (restauración tras pérdida/reinstalación).
- ``save_document``: escribe en el primario y hace push best-effort al espejo.
  Los errores del espejo nunca rompen la operación local; quedan registrados
  en ``last_error`` para que la UI los muestre.
"""

from __future__ import annotations

from typing import Optional

from repositories.base import BaseRepository, empty_document


def _has_content(document: dict) -> bool:
    return bool(document.get("jobs")) or bool(document.get("notes"))


class MirrorRepository(BaseRepository):
    def __init__(self, primary: BaseRepository, mirror: Optional[BaseRepository] = None):
        self.primary = primary
        self.mirror = mirror
        self.last_error: Optional[str] = None

    def attach_mirror(self, mirror: Optional[BaseRepository]) -> None:
        self.mirror = mirror
        self.last_error = None

    def load_document(self) -> dict:
        local = self.primary.load_document()
        if _has_content(local):
            return local
        if self.mirror is not None:
            try:
                pulled = self.mirror.load_document()
                if _has_content(pulled):
                    # Restaurar desde Drive: materializar local para no perderlo.
                    self.primary.save_document(pulled)
                    self.last_error = None
                    return pulled
            except Exception as exc:
                self.last_error = f"Respaldo no disponible: {exc}"
        return empty_document()

    def save_document(self, document: dict) -> None:
        self.primary.save_document(document)
        self.last_error = None
        if self.mirror is not None:
            try:
                self.mirror.save_document(document)
            except Exception as exc:
                self.last_error = f"Respaldo en Drive pendiente: {exc}"