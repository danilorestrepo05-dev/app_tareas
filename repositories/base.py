"""Patrón Repositorio: la lógica de negocio nunca conoce la capa física.

El almacenamiento es un *documento* JSON versionado (``{"schema_version",
"jobs": [...], "notes": [...]}``) para que los datos sean universales y se
puedan migrar sin pérdida. La interfaz es agnóstica: JSON local, Google Drive,
base relacional, etc., solo requieren una clase concreta.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


def empty_document() -> dict:
    return {"schema_version": 2, "jobs": [], "notes": []}


class BaseRepository(ABC):
    """Contrato de persistencia del documento de datos de un usuario."""

    @abstractmethod
    def load_document(self) -> dict:
        """Devuelve el documento completo (con migración al formato actual)."""

    @abstractmethod
    def save_document(self, document: dict) -> None:
        """Persiste el documento completo de forma atómica."""