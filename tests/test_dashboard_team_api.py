"""The chat front end talks to the CEO through /api/team/*."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import importlib

    import agent_reach.discovery.storage as storage_mod

    monkeypatch.setattr(storage_mod, "DEFAULT_DB_PATH", tmp_path / "api.db")
    import agent_reach.server.app as app_mod

    importlib.reload(app_mod)
    from fastapi.testclient import TestClient

    return TestClient(app_mod.app), app_mod


def test_ask_plans_the_work_and_status_follows(client):
    c, app_mod = client
    r = c.post("/api/team/ask", json={"message": "Find customers for https://tidewatch.example"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "find_customers" and body["mode"] == "host"
    d = body["directive_id"]
    status = c.get(f"/api/team/directives/{d}").json()
    assert status["tasks"][0]["role"] == "analyst"
    assert c.get("/api/team/directives").json()["directives"][0]["directive_id"] == d
    assert c.get(f"/api/team/directives/{d}/report").json()["verified_work"] == []
    assert len(c.get("/api/team/roster").json()["roles"]) >= 7


def test_unknown_directive_and_bad_checkpoint(client):
    c, _ = client
    assert c.get("/api/team/directives/nope").status_code == 400
    assert c.post("/api/team/tasks/nope/checkpoint", json={"decision": "approve", "message": "yes"}).status_code == 400
    assert c.post("/api/team/tasks/x/checkpoint", json={"decision": "maybe", "message": "yes"}).status_code == 422
    assert c.post("/api/team/ask", json={"message": "x"}).status_code == 422


def test_settings_never_store_credentials_in_the_database(client, tmp_path, monkeypatch):
    c, app_mod = client
    monkeypatch.setattr("agent_reach.config.Config.CONFIG_FILE", tmp_path / "cfg" / "config.yaml")
    r = c.post("/api/settings", json={
        "posting_settings": {"mode": "manual", "reddit_password": "hunter2", "github_token": "ghp_secret"},
        "llm_settings": {"provider": "anthropic", "model": "", "api_key": "sk-test-123"},
    })
    assert r.status_code == 200 and set(r.json()["ignored_credentials"]) == {"reddit_password", "github_token"}
    stored_posting = app_mod.storage.get_setting("posting_settings", {})
    stored_llm = app_mod.storage.get_setting("llm_settings", {})
    assert "hunter2" not in str(stored_posting) and "ghp_secret" not in str(stored_posting)
    assert "sk-test-123" not in str(stored_llm)
    shown = c.get("/api/settings").json()
    assert "sk-test-123" not in str(shown) and shown["llm_settings"]["has_api_key"] in (True, False)


def test_old_database_secrets_are_scrubbed_on_start(tmp_path):
    from agent_reach.discovery.storage import DiscoveryStorage

    path = tmp_path / "old.db"
    db = DiscoveryStorage(path)
    db.set_setting("posting_settings", {"mode": "manual", "reddit_password": "hunter2", "github_token": "t"})
    again = DiscoveryStorage(path)
    raw = again.get_setting("posting_settings", {})
    assert "hunter2" not in str(raw) and raw["mode"] == "manual"


def test_next_step_cancel_and_memory_endpoints(client):
    c, _ = client
    d = c.post("/api/team/ask", json={"message": "Find customers for https://tidewatch.example"}).json()["directive_id"]
    nxt = c.get(f"/api/team/directives/{d}/next").json()
    assert nxt["do"] == "work" and nxt["role"] == "analyst"
    assert c.post("/api/team/memory", json={"text": "Never pitch in a first reply."}).json()["remembered"] is True
    memories = c.get("/api/team/memory").json()["memories"]
    assert memories[0]["kind"] == "owner_preference"
    assert c.delete(f"/api/team/memory/{memories[0]['id']}").json()["forgotten"] is True
    assert c.post(f"/api/team/directives/{d}/cancel", json={"reason": "test"}).json()["status"] == "cancelled"
    assert c.post(f"/api/team/directives/{d}/cancel", json={}).status_code == 400
    assert c.post("/api/team/memory", json={"text": "short"}).status_code == 422


def test_dashboard_checkpoint_answers_are_recorded_as_the_owner_clicking(client):
    c, app_mod = client
    d = c.post("/api/team/ask", json={"message": "find customers"}).json()["directive_id"]
    task = next(t for t in app_mod.team.store.list_tasks(d) if t.kind == "checkpoint")
    assert c.post(f"/api/team/tasks/{task.id}/checkpoint", json={"decision": "approve", "message": "https://tidewatch.example"}).status_code == 200
    assert c.get(f"/api/team/directives/{d}/report").json()["owner_confirmations"][0]["via"] == "dashboard"
