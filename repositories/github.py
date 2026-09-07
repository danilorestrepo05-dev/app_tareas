"""Repositorio duradero en GitHub (repo privado) con copia local en caché.

Cada usuario tiene su documento en ``data/<email>.json`` dentro de un
repositorio privado, escrito con la **Contents API**. GitHub es la fuente de
verdad: sobrevive a reinicios del contenedor de Streamlit Cloud (los archivos
locales de los contenedores son efímeros). Si GitHub no responde, la app sigue
operando con una copia local en caché y **avisa** al usuario (nunca borra datos
en silencio).
"""

from __future__ import annotations

import base64
import json
import os
from typing import Optional
from urllib.parse import quote

from repositories.base import BaseRepository, empty_document

try:
    import httpx
except Exception:  # pragma: no cover - httpx es dependencia de Authlib
    httpx = None  # type: ignore

_API_BASE = "https://api.github.com"
_COMMIT_MSG = "NotesControl: actualizar datos"
_TIMEOUT = 15.0


def _normalize(data) -> dict:
    """Acepta listas (formato v1) o dicts; devuelve siempre el documento v2."""
    if isinstance(data, dict):
        return {
            "schema_version": data.get("schema_version", 2),
            "jobs": data.get("jobs") if isinstance(data.get("jobs"), list) else [],
            "notes": data.get("notes") if isinstance(data.get("notes"), list) else [],
        }
    if isinstance(data, list):
        return {"schema_version": 2, "jobs": data, "notes": []}
    return empty_document()


def _has_data(doc: dict) -> bool:
    return bool(doc.get("jobs") or doc.get("notes"))


def _describe_status(res: httpx.Response) -> str:
    snippet = ""
    try:
        body = res.json()
        snippet = body.get("message") or ""
    except Exception:
        snippet = ""
    if snippet:
        return f"GitHub respondió {res.status_code}: {snippet}"
    return f"GitHub respondió {res.status_code}"


class GithubRepository(BaseRepository):
    """Documento de un usuario persistido en ``repo/data/<email>.json``."""

    def __init__(
        self,
        token: str,
        repo: str,
        email: str,
        local_shadow: BaseRepository,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.token = token
        self.repo = repo
        self.email = email
        self.path = f"data/{quote(email, safe='/@._+-')}.json"
        self._shadow = local_shadow
        self._client = client or (httpx.Client(base_url=_API_BASE, timeout=_TIMEOUT) if httpx else None)
        if self._client is None:  # pragma: no cover - httpx siempre instala con Authlib
            raise RuntimeError("Falta la dependencia httpx para persistir en GitHub.")
        self._sha: Optional[str] = None
        self._dirty = False
        self.last_error: Optional[str] = None

    # -- Configuración ------------------------------------------------------
    @staticmethod
    def config_value() -> dict:
        """Lee la configuración ``[github]``: secrets de Streamlit o entorno."""
        env_token = os.environ.get("GITHUB_TOKEN")
        env_repo = os.environ.get("GITHUB_REPO")
        if env_token or env_repo:
            return {"token": env_token or "", "repo": env_repo or ""}
        try:
            import streamlit as st

            return dict(st.secrets.get("github") or {})
        except Exception:
            return {}

    @classmethod
    def try_build(cls, email: str) -> Optional["GithubRepository"]:
        """Crea el repositorio si hay config; si no, devuelve None (local)."""
        cfg = cls.config_value()
        token = (cfg.get("token") or "").strip()
        repo = (cfg.get("repo") or "").strip()
        if not token or not repo:
            return None
        from repositories.local_json import LocalJsonRepository

        uid = email.strip().lower()
        root = os.environ.get("APP_DATA_ROOT", ".data")
        shadow = LocalJsonRepository(os.path.join(root, uid, "trabajos.json"))
        return cls(token, repo, uid, shadow)

    # -- Helpers HTTP -------------------------------------------------------
    def _headers(self) -> dict:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _api_url(self) -> str:
        return f"/repos/{self.repo}/contents/{self.path}"

    # -- Lectura ------------------------------------------------------------
    def load_document(self) -> dict:
        # Hay una escritura local que GitHub aún no confirmó: no pisarla.
        if self._dirty:
            return self._shadow_doc()

        try:
            res = self._client.get(self._api_url(), headers=self._headers())
        except httpx.HTTPError as exc:
            self.last_error = (
                f"No se pudo conectar con GitHub "
                f"({exc.__class__.__name__}); usando la copia local."
            )
            return self._load_shadow_or_error()

        if res.status_code == 404:
            # GitHub no tiene el archivo: es la verdad; si hay copia local con
            # datos (periodo sin conexión), devuélvela.
            doc = self._shadow_doc()
            return doc if _has_data(doc) else empty_document()

        if res.status_code != 200:
            self.last_error = _describe_status(res)
            return self._load_shadow_or_error()

        try:
            payload = res.json()
            self._sha = payload["sha"]
            raw = base64.b64decode(payload["content"]).decode("utf-8")
            doc = _normalize(json.loads(raw))
        except Exception as exc:
            self.last_error = f"Respuesta inválida de GitHub; usando la copia local ({exc})."
            return self._load_shadow_or_error()

        self.last_error = None
        try:
            self._shadow.save_document(doc)
        except Exception:
            pass  # la caché es secundaria; el dato ya está en GitHub
        return doc

    def _shadow_doc(self) -> dict:
        try:
            return _normalize(self._shadow.load_document())
        except Exception:
            return empty_document()

    def _load_shadow_or_error(self) -> dict:
        doc = self._shadow_doc()
        if _has_data(doc):
            return doc
        raise RuntimeError(
            "GitHub no responde y no hay datos guardados localmente todavía. "
            "Reintenta en un momento; tu información está a salvo."
        )

    # -- Escritura ----------------------------------------------------------
    def save_document(self, document: dict) -> None:
        doc = _normalize(document)
        raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        content_b64 = base64.b64encode(raw).decode("ascii")

        # La copia local SIEMPRE primero: nunca perder la escritura.
        try:
            self._shadow.save_document(doc)
        except Exception as exc:
            raise RuntimeError(f"No se pudo guardar la copia local ({exc}).") from exc

        body = {"message": _COMMIT_MSG, "content": content_b64}
        if self._sha:
            body["sha"] = self._sha

        try:
            res = self._client.put(self._api_url(), headers=self._headers(), json=body)
        except httpx.HTTPError as exc:
            self._dirty = True
            raise RuntimeError(
                f"Guardado solo en local: GitHub no respondió "
                f"({exc.__class__.__name__}). Tu trabajo no se pierde: se "
                "sincronizará al recuperar la conexión."
            ) from exc

        if res.status_code in (409, 422):
            # Sha desactualizado (otra sesión/escritura): recarga y reintenta 1 vez.
            try:
                get = self._client.get(self._api_url(), headers=self._headers())
                if get.status_code == 200:
                    body["sha"] = get.json()["sha"]
                res = self._client.put(self._api_url(), headers=self._headers(), json=body)
            except httpx.HTTPError as exc:
                self._dirty = True
                raise RuntimeError(
                    f"Guardado solo en local: conﬂicto sin resolver en GitHub "
                    f"({exc.__class__.__name__})."
                ) from exc

        if res.status_code in (200, 201):
            try:
                self._sha = res.json()["content"]["sha"]
            except Exception:
                pass
            self._dirty = False
            self.last_error = None
            return

        self._dirty = True
        self.last_error = _describe_status(res)
        raise RuntimeError(f"Guardado solo en local: {self.last_error}.")