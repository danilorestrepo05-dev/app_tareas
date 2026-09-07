"""Tests del repositorio duradero de GitHub (Contents API + caché local).

Se usa ``httpx.MockTransport`` para simular la API sin red y un repositorio
local en un directorio temporal como caché.
"""

import base64
import json
import os

import httpx
import pytest

from repositories.base import BaseRepository, empty_document
from repositories.github import GithubRepository
from repositories.local_json import LocalJsonRepository

REPO = "owner/notascontrol-data"


def _b64(doc: dict) -> str:
    return base64.b64encode(json.dumps(doc).encode("utf-8")).decode("ascii")


def make_repo(handler, tmp_path) -> GithubRepository:
    shadow = LocalJsonRepository(str(tmp_path / "trabajos.json"))
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.com")
    return GithubRepository(token="tok", repo=REPO, email="usuario@mail.com", local_shadow=shadow, client=client)


def test_load_returns_empty_when_not_found(tmp_path):
    def handler(request):
        return httpx.Response(404, request=request)

    repo = make_repo(handler, tmp_path)
    assert repo.load_document() == empty_document()
    assert repo._sha is None


def test_load_reads_github_and_updates_shadow(tmp_path):
    doc = {"schema_version": 2, "jobs": [{"id": "j1"}], "notes": []}

    def handler(request):
        return httpx.Response(
            200,
            json={"sha": "aaa", "content": _b64(doc)},
            request=request,
        )

    repo = make_repo(handler, tmp_path)
    loaded = repo.load_document()
    assert loaded["jobs"][0]["id"] == "j1"
    assert repo._sha == "aaa"
    assert repo.last_error is None
    assert repo._shadow.load_document()["jobs"][0]["id"] == "j1"


def test_load_falls_back_to_shadow_when_github_down(tmp_path):
    shadow_doc = {"schema_version": 2, "jobs": [{"id": "local"}], "notes": []}
    shadow = LocalJsonRepository(str(tmp_path / "trabajos.json"))
    shadow.save_document(shadow_doc)

    def handler(request):
        raise httpx.ConnectError("red caída", request=request)

    repo = make_repo(handler, tmp_path)
    repo._shadow = shadow
    loaded = repo.load_document()
    assert loaded["jobs"][0]["id"] == "local"
    assert repo.last_error and "copia local" in repo.last_error


def test_load_raises_when_github_down_and_no_shadow(tmp_path):
    def handler(request):
        raise httpx.ConnectError("red caída", request=request)

    repo = make_repo(handler, tmp_path)
    with pytest.raises(RuntimeError, match="GitHub no responde"):
        repo.load_document()


def test_load_404_uses_shadow_with_data(tmp_path):
    shadow_doc = {"schema_version": 2, "jobs": [{"id": "offline"}], "notes": []}
    shadow = LocalJsonRepository(str(tmp_path / "trabajos.json"))
    shadow.save_document(shadow_doc)

    def handler(request):
        return httpx.Response(404, request=request)

    repo = make_repo(handler, tmp_path)
    repo._shadow = shadow
    assert repo.load_document()["jobs"][0]["id"] == "offline"


def test_save_creates_then_updates_with_sha(tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        if request.method == "PUT":
            return httpx.Response(
                201,
                json={"content": {"sha": "sha" + str(len(seen))}},
                request=request,
            )
        return httpx.Response(404, request=request)

    repo = make_repo(handler, tmp_path)
    repo.save_document({"schema_version": 2, "jobs": [{"id": "a"}], "notes": []})
    assert repo._sha == "sha1"

    repo.save_document({"schema_version": 2, "jobs": [{"id": "a", "estado": "nuevo"}], "notes": []})
    assert repo._sha == "sha2"

    put_bodies = [json.loads(r.content.decode("utf-8")) for r in seen if r.method == "PUT"]
    assert "sha" not in put_bodies[0]
    assert put_bodies[1]["sha"] == "sha1"
    assert repo.last_error is None
    assert not repo._dirty


def test_save_conflict_retries_with_fresh_sha(tmp_path):
    calls = {"puts": 0}

    def handler(request):
        if request.method == "PUT":
            calls["puts"] += 1
            if calls["puts"] == 1:
                return httpx.Response(409, json={"message": "sha conflict"}, request=request)
            return httpx.Response(201, json={"content": {"sha": "final"}}, request=request)
        return httpx.Response(200, json={"sha": "fresh"}, request=request)

    repo = make_repo(handler, tmp_path)
    repo.save_document(empty_document())
    assert calls["puts"] == 2
    assert repo._sha == "final"
    assert not repo._dirty


def test_save_github_error_keeps_shadow_and_raises(tmp_path):
    def handler(request):
        if request.method == "PUT":
            raise httpx.ConnectError("red caída", request=request)
        return httpx.Response(404, request=request)

    repo = make_repo(handler, tmp_path)
    doc = {"schema_version": 2, "jobs": [{"id": "j"}], "notes": []}
    with pytest.raises(RuntimeError, match="solo en local"):
        repo.save_document(doc)
    assert repo._dirty
    # La copia local guardó; el siguiente load devuelve esa (sin pisarla).
    assert repo.load_document()["jobs"][0]["id"] == "j"


def test_save_rejected_by_github_keeps_shadow_and_raises(tmp_path):
    def handler(request):
        if request.method == "PUT":
            return httpx.Response(422, json={"message": "invalid"}, request=request)
        return httpx.Response(404, request=request)

    repo = make_repo(handler, tmp_path)
    with pytest.raises(RuntimeError, match="422"):
        repo.save_document(empty_document())
    assert repo._dirty
    assert repo.last_error and "422" in repo.last_error


def test_try_build_with_env(monkeypatch, tmp_path, _unused_data_root):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    assert GithubRepository.try_build("a@b.com") is None

    monkeypatch.setenv("GITHUB_TOKEN", "tok")
    monkeypatch.setenv("GITHUB_REPO", REPO)
    repo = GithubRepository.try_build("  Usuario@Mail.com ")
    assert repo is not None
    assert repo.path == "data/usuario@mail.com.json"
    assert repo.email == "usuario@mail.com"


@pytest.fixture
def _unused_data_root(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DATA_ROOT", str(tmp_path / "data"))
    yield