"""Resource use: idle connections, lock cleanup, config reads and query plans."""

from __future__ import annotations

import gc
import os
from pathlib import Path

import pytest

from agent_reach.discovery import storage as storage_mod
from agent_reach.discovery.llm_client import LLMClient
from agent_reach.discovery.storage import DiscoveryStorage


def test_wal_file_survives_between_calls(tmp_path: Path):
    st = DiscoveryStorage(tmp_path / "a.db")
    st.set_setting("k", {"v": 1})
    st.get_setting("k")
    assert (tmp_path / "a.db-wal").exists()   # an idle connection keeps it, so no checkpoint per call
    assert st.get_setting("k") == {"v": 1}
    st.close()


def test_close_releases_the_idle_connection_and_storage_keeps_working(tmp_path: Path):
    st = DiscoveryStorage(tmp_path / "b.db")
    st.close()
    assert str(tmp_path / "b.db") not in storage_mod._anchors
    st.set_setting("k", 2)
    assert st.get_setting("k") == 2


def test_idle_connections_are_bounded(tmp_path: Path):
    stores = [DiscoveryStorage(tmp_path / f"db{i}.db") for i in range(storage_mod._ANCHOR_LIMIT + 5)]
    assert len(storage_mod._anchors) <= storage_mod._ANCHOR_LIMIT
    for st in stores:   # an evicted database still works
        st.set_setting("k", 1)
        assert st.get_setting("k") == 1
    for st in stores:
        st.close()


def test_recreated_database_file_gets_a_fresh_idle_connection(tmp_path: Path):
    path = tmp_path / "c.db"
    st = DiscoveryStorage(path)
    st.set_setting("k", 1)
    st.close()  # release idle connection before file removal (essential on Windows)
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(str(path) + suffix)
        except FileNotFoundError:
            pass
    fresh = DiscoveryStorage(path)
    assert fresh.get_setting("k") is None
    fresh.set_setting("k", 3)
    assert fresh.get_setting("k") == 3
    fresh.close()


def test_directive_locks_are_released_when_unused(make_engine):
    engine = make_engine()
    for i in range(5):
        did = engine.open_directive(f"Find customers for https://site{i}.example")["directive_id"]
        with engine._lock(did):
            pass
        with engine._evidence_lock(did):
            pass
    gc.collect()
    assert len(engine._locks) == 0 and len(engine._ev_locks) == 0


def test_a_held_lock_is_shared_by_a_second_caller(make_engine):
    engine = make_engine()
    first = engine._lock("d1")
    assert engine._lock("d1") is first
    assert not first.acquire(blocking=False) or first.release() is None


def test_llm_client_reads_the_config_file_once(monkeypatch: pytest.MonkeyPatch):
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY",
                 "DEEPSEEK_API_KEY", "LLM_PROVIDER", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    loads = []
    from agent_reach import config as config_mod

    real_init = config_mod.Config.__init__

    def counting_init(self, *a, **kw):
        loads.append(1)
        real_init(self, *a, **kw)

    monkeypatch.setattr(config_mod.Config, "__init__", counting_init)
    LLMClient()
    assert len(loads) <= 1


def test_newest_first_lists_use_an_index(storage: DiscoveryStorage):
    from agent_reach.team.store import TeamStore

    TeamStore(storage)
    plans = {
        "SELECT data FROM discovered_items ORDER BY created_at DESC LIMIT 20": "idx_discovered_created",
        "SELECT data FROM discovered_items WHERE platform='reddit' ORDER BY created_at DESC LIMIT 20": "idx_discovered_platform_created",
        "SELECT data FROM replies ORDER BY created_at DESC LIMIT 20": "idx_replies_created",
        "SELECT data FROM team_tasks WHERE status = 'running'": "idx_team_tasks_status",
        "SELECT data FROM team_directives ORDER BY created_at DESC LIMIT 20": "idx_team_directives_created",
    }
    with storage._connection() as conn:
        for sql, index in plans.items():
            detail = " ".join(str(r[3]) for r in conn.execute("EXPLAIN QUERY PLAN " + sql))
            assert index in detail, (sql, detail)


def test_sync_mode_env_is_optional(tmp_path: Path):
    assert storage_mod._SYNC_MODE in ("", "NORMAL", "OFF", "EXTRA")


def test_numeric_settings_round_trip(storage: DiscoveryStorage):
    storage.set_setting("n", 7)
    storage.set_setting("f", 1.5)
    storage.set_setting("t", True)
    storage.set_setting("s", "text")
    storage.set_setting("d", {"a": [1, 2]})
    assert storage.get_setting("n") == 7 and storage.get_setting("f") == 1.5
    assert storage.get_setting("t") is True and storage.get_setting("s") == "text"
    assert storage.get_setting("d") == {"a": [1, 2]}
