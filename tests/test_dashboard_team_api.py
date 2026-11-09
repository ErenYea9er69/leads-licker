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


def test_accounts_api(client):
    c, _ = client
    # Initially empty or default
    r = c.get("/api/accounts")
    assert r.status_code == 200
    assert "accounts" in r.json()

    # Link account
    r_link = c.post("/api/accounts", json={
        "platform": "reddit",
        "handle": "founder_john",
        "alias": "alt1",
        "focus": ["r/saas", "r/startups"],
        "mode": "manual",
    })
    assert r_link.status_code == 200
    assert r_link.json()["ok"] is True

    # Check listed
    r_list = c.get("/api/accounts").json()
    assert any(a["handle"] == "founder_john" and a["platform"] == "reddit" for a in r_list["accounts"])

    # Set voice
    r_voice = c.post("/api/accounts/reddit/founder_john/voice", json={
        "samples": ["Hey, that sounds like a common issue. I usually solve it with a webhook."]
    })
    assert r_voice.status_code == 200

    # Unlink
    r_unlink = c.delete("/api/accounts/reddit/founder_john")
    assert r_unlink.status_code == 200
    assert r_unlink.json()["ok"] is True


def test_connections_api(client):
    c, _ = client
    r = c.get("/api/connections")
    assert r.status_code == 200
    body = r.json()
    assert "sources" in body
    names = {s["source"] for s in body["sources"]}
    assert {"reddit", "youtube", "hackernews", "web", "twitter", "github", "quora", "model"}.issubset(names)


def test_voice_lint_and_disclosures_api(client):
    c, _ = client
    r_disc = c.get("/api/voice/disclosures")
    assert r_disc.status_code == 200
    assert len(r_disc.json()["phrases"]) > 0

    r_lint = c.post("/api/voice/lint", json={
        "text": "Honestly this is totally game-changing! It's not just a tool, it's a revolution -- check it out.",
        "platform": "reddit",
        "kind": "value_first",
    })
    assert r_lint.status_code == 200
    lint_res = r_lint.json()
    assert "issues" in lint_res
    assert lint_res["passed"] is False  # contains buzzwords, contrast frame, double dash


def test_team_intake_api(client):
    c, _ = client
    r = c.get("/api/team/intake")
    assert r.status_code == 200
    st = r.json()
    assert "ask_next" in st
    assert "collected" in st

    r_turn = c.post("/api/team/intake", json={
        "answers": {"product": "Automated invoice reminders for freelancers"}
    })
    assert r_turn.status_code == 200
    turn_res = r_turn.json()
    assert "product" in turn_res["collected"]

    # Test reset
    r_del = c.delete("/api/team/intake")
    assert r_del.status_code == 200
    del_res = r_del.json()
    assert "product" not in del_res["collected"]
