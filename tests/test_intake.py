"""The CEO interview, the search it starts in the background, and the connections guide."""

from __future__ import annotations

import pytest

from agent_reach.discovery import connections
from agent_reach.discovery.harvester import CommunityHarvester
from agent_reach.discovery.models import DiscoveredItem
from agent_reach.team import intake as intake_mod
from agent_reach.team.intake import Intake

PRODUCT = "Tidewatch sends automatic invoice reminders to clients who pay late."
USERS = "Freelance designers who bill clients by invoice."


@pytest.fixture()
def fake_search(monkeypatch):
    """Every query returns two fresh threads. The test records the queries."""
    calls = []

    def execute_query(self, query, limit=5):
        calls.append((query.platform, query.query))
        out = []
        for i in range(2):
            item = DiscoveredItem(
                url=f"https://example.com/{query.platform}/{abs(hash(query.query)) % 10**6}/{i}", platform=query.platform,
                community="r/freelance" if query.platform == "reddit" else "site", author="a", title="t", content="c",
            )
            if self.storage.save_discovered_item(item):
                out.append(item)
        return out

    monkeypatch.setattr(CommunityHarvester, "execute_query", execute_query)
    return calls


@pytest.fixture()
def intake(svc, make_engine):
    intake_mod._RUNNING.clear()
    return Intake(lambda: svc, make_engine())


def test_nothing_starts_before_product_and_target_users(intake, fake_search):
    out = intake.turn({"product": PRODUCT}, wait=True)
    assert out["started_now"] == [] and fake_search == []
    assert [m["key"] for m in out["missing_required"]] == ["target_users"]
    assert out["ask_next"][0]["key"] == "target_users" and not out["ready_for_pipeline"]


def test_search_starts_once_the_two_required_answers_are_in(intake, fake_search):
    out = intake.turn({"product": PRODUCT, "target_users": USERS}, wait=True)
    assert len(out["started_now"]) == 3   # reddit, hackernews, web by default
    assert {p for p, _ in fake_search} == {"reddit", "hackernews", "web"}
    assert all(j["status"] == "done" and j["threads"] > 0 for j in out["jobs"])
    assert out["prefetched_threads"] == sum(j["threads"] for j in out["jobs"])
    assert "background" in out["tell_owner"] and "Reddit" in out["tell_owner"]


def test_owner_named_platforms_decide_the_search(intake, fake_search):
    intake.turn({"product": PRODUCT, "target_users": USERS, "platforms": "Reddit, YouTube and X mostly"}, wait=True)
    assert {p for p, _ in fake_search} == {"reddit", "youtube", "twitter"}


def test_questions_unrelated_to_the_market_come_first_after_the_search_starts(intake, fake_search):
    out = intake.turn({"product": PRODUCT, "target_users": USERS}, wait=True)
    keys = [q["key"] for q in out["ask_next"]]
    assert keys == ["site", "accounts"]   # not problems, platforms or competitors


def test_same_facts_do_not_search_again_but_new_facts_do(intake, fake_search):
    intake.turn({"product": PRODUCT, "target_users": USERS}, wait=True)
    first = len(fake_search)
    intake.turn({"language": "English, selling in the US and Canada"}, wait=True)
    assert len(fake_search) == first
    out = intake.turn({"problems": "Clients pay me late again. I chase invoices every month."}, wait=True)
    assert len(fake_search) > first and out["started_now"]


def test_search_runs_are_capped(intake, fake_search):
    for i in range(6):
        intake.turn({"problems": f"Clients pay late in a new way number {i}."} if i else {"product": PRODUCT, "target_users": USERS}, wait=True)
    assert intake.state()["runs"] == intake_mod.MAX_RUNS


def test_one_failing_source_does_not_stop_the_others(intake, monkeypatch, fake_search):
    real = CommunityHarvester.execute_query

    def flaky(self, query, limit=5):
        if query.platform == "hackernews":
            raise RuntimeError("boom")
        return real(self, query, limit)

    monkeypatch.setattr(CommunityHarvester, "execute_query", flaky)
    out = intake.turn({"product": PRODUCT, "target_users": USERS}, wait=True)
    status = {j["platform"]: j["status"] for j in out["jobs"]}
    assert status == {"reddit": "done", "hackernews": "failed", "web": "done"}


def test_empty_results_from_failing_providers_count_as_a_failure(intake, monkeypatch):
    def broken(self, query, limit=5):
        self.diagnostics["search_error:exa"] += 1
        return []

    monkeypatch.setattr(CommunityHarvester, "execute_query", broken)
    out = intake.turn({"product": PRODUCT, "target_users": USERS}, wait=True)
    assert {j["status"] for j in out["jobs"]} == {"failed"} and "search calls failed" in out["jobs"][0]["summary"]


def test_a_search_that_simply_finds_nothing_is_done(intake, monkeypatch):
    monkeypatch.setattr(CommunityHarvester, "execute_query", lambda self, query, limit=5: [])
    out = intake.turn({"product": PRODUCT, "target_users": USERS}, wait=True)
    assert {j["status"] for j in out["jobs"]} == {"done"} and out["jobs"][0]["threads"] == 0


def test_a_job_with_no_live_thread_reads_as_interrupted(intake, svc):
    svc.storage.set_setting(intake_mod.STATE_KEY, {"facts": {}, "jobs": [{"id": "x:reddit", "run_id": "x", "platform": "reddit", "status": "running"}]})
    assert intake.state()["jobs"][0]["status"] == "interrupted"


def test_unknown_and_empty_answers_are_rejected(intake):
    out = intake.turn({"colour": "blue", "product": " ", "site": "https://tidewatch.example"})
    assert "colour" in out["rejected"] and "product" in out["rejected"] and out["accepted"] == ["site"]


def test_rules_become_memory_once(intake):
    intake.turn({"rules": "Never mention pricing in a first reply. Never use the word synergy."})
    intake.turn({"rules": "Never mention pricing in a first reply. Never use the word synergy."})
    memory = intake.engine.recall()
    assert sum("pricing" in str(m) for m in memory["memories"]) == 1 and sum("synergy" in str(m) for m in memory["memories"]) == 1


def test_answers_that_need_a_tool_tell_the_host_which(intake):
    out = intake.turn({"accounts": "u/alpha and u/beta on Reddit", "voice": "here are some of my comments", "language": "English"})
    text = " ".join(out["actions_for_you"])
    assert "reach_link_account" in text and "reach_set_voice_samples" in text and "reach_set_reply_preferences" in text


def test_ready_after_search_finishes_and_request_uses_only_owner_words(intake, fake_search):
    out = intake.turn({"product": PRODUCT, "target_users": USERS, "problems": "Clients pay me late again."}, wait=True)
    assert out["ready_for_pipeline"] is False or out["suggested_request"]
    assert PRODUCT in intake_mod.suggested_request(intake.state()["facts"])
    assert "Clients pay me late again." in intake_mod.suggested_request(intake.state()["facts"])


def test_server_model_opens_the_plan_in_the_background(intake, fake_search, monkeypatch):
    started = []
    monkeypatch.setattr(intake.engine, "llm_ready", lambda: True)
    monkeypatch.setattr(intake.engine, "run", lambda did, **k: started.append(did) or {})
    out = intake.turn({"product": PRODUCT, "target_users": USERS}, wait=True)
    import time

    time.sleep(0.1)
    assert out["directive_id"] and started == [out["directive_id"]]
    assert "profile" in out["tell_owner"]


def test_host_mode_opens_no_plan(intake, fake_search):
    out = intake.turn({"product": PRODUCT, "target_users": USERS}, wait=True)
    assert out["directive_id"] is None


def test_work_order_carries_the_owner_answers(intake, fake_search):
    intake.turn({"product": PRODUCT, "target_users": USERS}, wait=True)
    opened = intake.engine.open_directive(intake_mod.suggested_request(intake.state()["facts"]), intent="find_customers")
    order = intake.engine.work_order(directive_id=opened["directive_id"])
    assert order["work_order"]["owner_said"]["product"] == PRODUCT and "owner_said_note" in order["work_order"]


# ── The scout claims what the intake found ──

def test_a_prefetched_thread_reaches_the_scout_once(storage):
    item = DiscoveredItem(url="https://example.com/t/1", platform="web", community="c", author="a", title="t", content="c")
    storage.save_discovered_item(item)
    storage.mark_prefetched(item.id)
    assert not storage.is_url_discovered(item.url)   # new to the scout
    again = DiscoveredItem(url="https://example.com/t/1", platform="web", community="c", author="a", title="t2", content="c2")
    assert storage.save_discovered_item(again)       # the scout's harvest claims it
    assert storage.get_discovered_item(again.id).title == "t2" and storage.get_discovered_item(item.id) is None
    assert storage.is_url_discovered(item.url) and not storage.save_discovered_item(
        DiscoveredItem(url=item.url, platform="web", community="c", author="a", title="t3", content="c3"))
    assert storage.count_prefetched() == 0


# ── Connections ──

def test_every_source_has_a_report(svc):
    data = connections.connections("", svc.accounts)
    assert {s["source"] for s in data["sources"]} >= {"reddit", "youtube", "hackernews", "twitter", "github", "quora", "web", "model"}
    for s in data["sources"]:
        assert s["status"] in ("ready", "partial") and s["works_without_setup"] and "limits" in s


def test_aliases_and_unknown_source(svc):
    assert connections.connections("X", svc.accounts)["sources"][0]["source"] == "twitter"
    assert "error" in connections.connections("myspace", svc.accounts)


def test_connections_show_set_and_missing_without_values(svc, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "SECRET-VALUE-123")
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    yt = connections.connections("youtube", svc.accounts)["sources"][0]
    assert yt["search_with_api"] is True and any(v["name"] == "YOUTUBE_API_KEY" and v["set"] for v in yt["read_variables"])
    assert "SECRET-VALUE-123" not in str(connections.connections("", svc.accounts))
    web = connections.connections("web", svc.accounts)["sources"][0]
    assert any(v["name"] == "SERPER_API_KEY" and not v["set"] for v in web["read_variables"])


def test_reddit_report_lists_every_account_and_what_it_lacks(svc, monkeypatch):
    for name in ("CLIENT_ID", "CLIENT_SECRET", "USERNAME", "PASSWORD"):
        monkeypatch.delenv(f"REDDIT_{name}", raising=False)
        monkeypatch.delenv(f"REDDIT_ALT1_{name}", raising=False)
    svc.accounts.link("reddit", "alpha_user")
    svc.accounts.link("reddit", "beta_user", alias="alt1")
    monkeypatch.setenv("REDDIT_ALT1_CLIENT_ID", "id")
    rep = connections.connections("reddit", svc.accounts)["sources"][0]
    assert rep["accounts_linked"] == 2
    beta = next(a for a in rep["accounts"] if a["id"] == "reddit:beta_user")["credentials"]
    names = {v["name"]: v["set"] for v in beta["variables"]}
    assert names["REDDIT_ALT1_CLIENT_ID"] is True and names["REDDIT_ALT1_PASSWORD"] is False and not beta["ready"]
    alpha = next(a for a in rep["accounts"] if a["id"] == "reddit:alpha_user")["credentials"]
    assert any(v["name"] == "REDDIT_ALPHA_USER_CLIENT_ID" and v["also_read"] == "REDDIT_CLIENT_ID" for v in alpha["variables"])


# ── MCP surface ──

def test_new_tools_are_registered_and_visible_in_company_mode():
    import asyncio

    from agent_reach.mcp import server, team_tools
    from agent_reach.team.roles import WORKER_ONLY_TOOLS

    async def names():
        tools = await server.mcp.list_tools()
        return {t.name for t in tools}

    registered = asyncio.run(names())
    for name in ("ceo_intake", "reach_connections", "reach_list_accounts"):
        assert name in registered and name not in WORKER_ONLY_TOOLS
    assert team_tools.get_intake is not None
