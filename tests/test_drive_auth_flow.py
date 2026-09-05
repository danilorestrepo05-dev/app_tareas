"""Helpers del flujo OAuth de Drive: pendiente persistido en disco.

En Community Cloud la redirección de Google no restaura `st.session_state`,
así que el estado del flujo se persiste en `.credentials/pending_oauth_*.json`.
"""

from __future__ import annotations

import os
import time

import pytest

import auth.auth as auth_mod


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