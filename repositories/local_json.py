"""Repositorio local en un archivo JSON con Safe-Write (shadow-write).

Los datos se escriben primero en un archivo temporal y luego se reemplaza el
real con ``os.replace`` (operación atómica), con ``try/except`` defensivo.
Incluye migración automática del formato antiguo (lista de trabajos) al
documento versionado actual (``{"schema_version": 2, "jobs": [...], ...}``).
"""

from __future__ import annotations

import json
import os

from repositories.base import BaseRepository, empty_document, normalize_document


class LocalJsonRepository(BaseRepository):
    def __init__(self, path: str) -> None:
        self.path = os.path.abspath(path)

    def load_document(self) -> dict:
        if not os.path.exists(self.path):
            return empty_document()
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                return normalize_document(json.load(fh))
        except (OSError, json.JSONDecodeError):
            # Archivo ausente o corrupto: nunca romper la app.
            return empty_document()

    def save_document(self, document: dict) -> None:
        normalized = normalize_document(document)
        tmp_path = f"{self.path}.tmp"
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        try:
            with open(tmp_path, "w", encoding="utf-8") as fh:
                json.dump(normalized, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.path)
        except OSError as exc:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise RuntimeError(f"No se pudo guardar el archivo local: {exc}") from exc