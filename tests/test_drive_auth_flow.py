"""Helpers del flujo OAuth de Drive: pendiente persistido en disco.

En Community Cloud la redirección de Google no restaura `st.session_state`,
así que el estado del flujo se persiste en `.credentials/pending_oauth_*.json`.
"""

from __future__ import annotations

import os
import sys
import time

import pytest

import auth.auth as auth_mod


class _FakeQueryParams(dict):
    pass


class _FakeSessionState(dict):
    pass


class _FakeStreamlit:
    secrets = {"drive_oauth": {"redirect_uri": "http://localhost:8501"}}
    query_params = _FakeQueryParams()
    session_state = _FakeSessionState()

    @classmethod
    def set_query(cls, **kwargs):
        cls.query_params = _FakeQueryParams(kwargs)

    @classmethod
    def set_session(cls, **kwargs):
        cls.session_state = _FakeSessionState(kwargs)


def _inject_fake_streamlit(monkeypatch):
    monkeypatch.setitem(sys.modules, "streamlit", _FakeStreamlit)


class _FakeFlowFactory:
    STATE = "estado-de-prueba-xyz"

    class _Flow:
        credentials = "credenciales-fake"

        def __init__(self, state):
            self.state = state

        def authorization_url(self, **kwargs):  # noqa: ARG002
            return (f"https://accounts.google.com/o/oauth2/auth?state={self.state}", self.state)

        def fetch_token(self, authorization_response):  # noqa: ARG002
            return {"access_token": "tok"}

    def __call__(self, redirect_uri):  # noqa: ARG002
        return self._Flow(self.STATE)


def test_full_flow_start_then_callback(tmp_path, monkeypatch):
    """start_drive_auth persiste en disco y complete_drive_auth lo lee de ahí."""
    _inject_fake_streamlit(monkeypatch)
    monkeypatch.setattr(auth_mod, "CRED_DIR", str(tmp_path))
    monkeypatch.setattr(auth_mod, "_build_flow", _FakeFlowFactory())

    saved = []
    monkeypatch.setattr(auth_mod, "_save_token", lambda email, creds: saved.append((email, creds)))

    auth_url = auth_mod.start_drive_auth("usuario@test.com")
    assert auth_url and _FakeFlowFactory.STATE in auth_url

    pend = auth_mod._load_pending(_FakeFlowFactory.STATE, str(tmp_path))
    assert pend and pend["state"] == _FakeFlowFactory.STATE

    # Callback: nueva navegación, sin session_state (reinicio completo).
    _FakeStreamlit.set_session()
    _FakeStreamlit.set_query(code="code-ejemplo", state=_FakeFlowFactory.STATE)
    ok = auth_mod.complete_drive_auth()
    assert ok is True
    assert saved == [("usuario@test.com", "credenciales-fake")]
    assert "code" not in _FakeStreamlit.query_params
    assert auth_mod._load_pending(_FakeFlowFactory.STATE, str(tmp_path)) is None


def test_callback_without_pending_sets_friendly_error(tmp_path, monkeypatch):
    """Si no hay flujo pendiente (app reiniciada/redeploy), error claro y nada se rompe."""
    _inject_fake_streamlit(monkeypatch)
    monkeypatch.setattr(auth_mod, "_build_flow", _FakeFlowFactory())
    monkeypatch.setattr(auth_mod, "_save_token", lambda email, creds: None)

    _FakeStreamlit.set_session()
    _FakeStreamlit.set_query(code="code-huerfano", state="estado-desconocido")
    ok = auth_mod.complete_drive_auth()
    assert ok is False
    assert _FakeStreamlit.session_state.get("_drive_oauth_error")
    assert "Conectar Google Drive" in _FakeStreamlit.session_state["_drive_oauth_error"]


def test_pending_roundtrip_and_clear(tmp_path):
    state = "warehouse-1"
    payload = {"email": "a@b.c", "state": state, "redirect_uri": "https://x.app/cb", "ts": "ts"}
    auth_mod._save_pending(state, payload, str(tmp_path))
    assert auth_mod._load_pending(state, str(tmp_path)) == payload

    auth_mod._clear_pending(state, str(tmp_path))
    assert auth_mod._load_pending(state, str(tmp_path)) is None


def test_pending_path_is_stable_and_per_state(tmp_path):
    p1 = auth_mod._pending_path("estado-uno", str(tmp_path))
    p2 = auth_mod._pending_path("estado-uno", str(tmp_path))
    p3 = auth_mod._pending_path("estado-dos", str(tmp_path))
    assert p1 == p2
    assert p1 != p3
    assert p1.startswith(str(tmp_path))


def test_pending_ignores_corrupt_json(tmp_path):
    state = "corrupto"
    path = auth_mod._pending_path(state, str(tmp_path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{no es json")
    assert auth_mod._load_pending(state, str(tmp_path)) is None


def test_sweep_removes_expired_keeps_fresh(tmp_path):
    auth_mod._save_pending("viejo", {"state": "viejo"}, str(tmp_path))
    auth_mod._save_pending("nuevo", {"state": "nuevo"}, str(tmp_path))

    old_path = auth_mod._pending_path("viejo", str(tmp_path))
    past = time.time() - 60 * 60
    os.utime(old_path, (past, past))

    auth_mod._sweep_pending(str(tmp_path), max_age_minutes=10)
    assert auth_mod._load_pending("viejo", str(tmp_path)) is None
    assert auth_mod._load_pending("nuevo", str(tmp_path)) is not None


def test_sweep_missing_dir_is_noop(tmp_path):
    auth_mod._sweep_pending(str(tmp_path / "no-existe"), max_age_minutes=10)