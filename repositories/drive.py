"""Repositorio en Google Drive usando el scope `drive.file` (carpeta oculta).

La carpeta `appDataFolder` es invisible para el usuario y accesible solo por
esta app: ideal para que el respaldo sobreviva a pérdida/deterioro del
teléfono sin exponer los datos en el Drive de usuario.

Degradación elegante: si las librerías de Google no están instaladas o la
conexión falla, se reporta el error en lugar de romper la app (ver
``MirrorRepository``).
"""

from __future__ import annotations

from io import BytesIO
from typing import Optional

from repositories.base import BaseRepository, empty_document

try:  # Dependencias opcionales: la app funciona aunque falten.
    from googleapiclient.discovery import build as _gapic_build
    from googleapiclient.http import MediaIoBaseUpload

    _GOOGLE_IMPORTS_OK = True
except Exception:  # pragma: no cover - depende del entorno de ejecución
    _GOOGLE_IMPORTS_OK = False
    _gapic_build = None
    MediaIoBaseUpload = None

BACKUP_FILE_NAME = "registro_trabajos.json"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"
APP_DATA_FOLDER = "appDataFolder"


class DriveNotAvailableError(RuntimeError):
    """Indica que Drive no está disponbile (no autorizado o sin librerías)."""


def build_service(credentials) -> object:
    if not _GOOGLE_IMPORTS_OK:
        raise DriveNotAvailableError(
            "Librerías de Google no instaladas (google-api-python-client)."
        )
    return _gapic_build("drive", "v3", credentials=credentials, cache_discovery=False)


class DriveRepository(BaseRepository):
    """Persistencia en `appDataFolder` (carpeta oculta) de Google Drive."""

    def __init__(self, service: object, filename: str = BACKUP_FILE_NAME) -> None:
        self.service = service
        self.filename = filename

    def _find_file_id(self) -> Optional[str]:
        query = (
            f"name = '{self.filename}' and 'appDataFolder' in parents "
            "and trashed = false"
        )
        result = (
            self.service.files()
            .list(
                q=query,
                fields="files(id, name)",
                pageSize=10,
                spaces=APP_DATA_FOLDER,
            )
            .execute()
        )
        files = result.get("files", [])
        return files[0]["id"] if files else None

    def load_document(self) -> dict:
        file_id = self._find_file_id()
        if not file_id:
            return empty_document()
        content = self.service.files().get_media(fileId=file_id).execute()
        try:
            import json

            data = json.loads(content.decode("utf-8"))
            if isinstance(data, list):  # formato antiguo
                return {"schema_version": 2, "jobs": data, "notes": []}
            return data if isinstance(data, dict) else empty_document()
        except (ValueError, UnicodeDecodeError):
            return empty_document()

    def save_document(self, document: dict) -> None:
        if MediaIoBaseUpload is None:
            raise DriveNotAvailableError("Librerías de Google no disponibles.")
        import json

        payload = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
        media = MediaIoBaseUpload(BytesIO(payload), mimetype="application/json")
        file_id = self._find_file_id()
        if file_id:
            self.service.files().update(fileId=file_id, media_body=media).execute()
        else:
            body = {"name": self.filename, "parents": [APP_DATA_FOLDER]}
            self.service.files().create(body=body, media_body=media, fields="id").execute()