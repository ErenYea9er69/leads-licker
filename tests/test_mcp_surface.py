"""The MCP surface: tools only, no prompts, company mode hides specialist tools."""

from __future__ import annotations

import pytest

from agent_reach.mcp import server, team_tools
from agent_reach.team.roles import RESTRICTED_TOOLS, WORKER_ONLY_TOOLS
from tests.conftest import run


@pytest.fixture()
def full_tools():
    return {t.name for t in run(server.mcp.list_tools())}


def test_server_registers_no_prompts():
    assert run(server.mcp.list_prompts()) == []


def test_ceo_tools_exist(full_tools):
    expected = {
        "ceo_open_directive", "ceo_status", "ceo_run", "ceo_next_work_order", "ceo_call_tool", "ceo_submit_result",
        "ceo_resolve_checkpoint", "ceo_create_task", "ceo_update_task", "ceo_hire_specialist", "ceo_create_playbook",
        "ceo_list_team", "ceo_report", "ceo_next_step", "ceo_cancel_directive", "ceo_memory",
    }
    assert expected <= full_tools


def test_every_worker_only_tool_is_a_real_tool(full_tools):
    assert WORKER_ONLY_TOOLS <= full_tools
    assert RESTRICTED_TOOLS <= full_tools


def test_company_mode_hides_specialist_tools_and_keeps_owner_tools(monkeypatch):
    # Work on a throwaway server so the shared one keeps every tool for the other tests.
    from agent_reach.mcp import compat

    fresh = compat.make_server("t", "t")
    for t in run(server.mcp.list_tools()):
        fresh.add_tool(server.mcp._tool_manager.get_tool(t.name).fn, name=t.name)
    monkeypatch.setattr(team_tools, "mcp", fresh)
    assert team_tools.apply_mode("company") == "company"
    names = {t.name for t in run(fresh.list_tools())}
    assert not (names & WORKER_ONLY_TOOLS)
    assert {"reach_approve_reply", "reach_publish_reply", "reach_confirm_posted", "reach_status", "ceo_open_directive"} <= names
    assert team_tools.apply_mode("bogus") == "company"
    assert team_tools.apply_mode("full") == "full"


def test_host_drives_the_company_through_mcp_tool_functions(svc, make_engine, monkeypatch):
    monkeypatch.setattr(team_tools, "_engine", make_engine())
    opened = team_tools.ceo_open_directive("Find customers for https://tidewatch.example")
    assert opened["mode"] == "host" and opened["intent"] == "find_customers"
    d = opened["directive_id"]
    order = team_tools.ceo_next_work_order(directive_id=d)
    assert order["role"]["name"] == "analyst" and "Company rules" in order["system_prompt"]
    task_id = order["work_order"]["task_id"]
    fetched = team_tools.ceo_call_tool(task_id, "reach_fetch_site_text", {"url": "https://tidewatch.example"})
    assert fetched["ok"] and fetched["evidence_id"] == "E1"
    refused = team_tools.ceo_call_tool(task_id, "reach_publish_reply", {"reply_id": "x"})
    assert not refused["ok"]
    bad = team_tools.ceo_submit_result(task_id, {"summary": "done", "claims": [{"text": "Tidewatch is great", "evidence_ids": ["E1"], "quote": "Tidewatch is the best ever"}], "data": {}})
    assert not bad["accepted"] and bad["attempts_left"] == 2
    status = team_tools.ceo_status(d)
    assert status["tasks"][0]["status"] == "running"
    team = team_tools.ceo_list_team(include_tools=True)
    assert {r["name"] for r in team["roles"]} >= {"analyst", "scout", "qualifier", "writer", "editor", "strategist", "researcher", "follow_up", "inspector"}
    assert "tool_catalog" in team
    report = team_tools.ceo_report(d)
    assert report["verified_work"] == []
