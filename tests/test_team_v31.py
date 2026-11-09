"""Company layer 3.1: honest empty results, planning, memory, recovery, the editor loop and the new members."""

from __future__ import annotations

import time
from typing import Any, Dict

from agent_reach.team.toolbox import _def_from
from tests.conftest import FakeLLM
from tests.test_team_engine import (
    GOOD_REPLY,
    REQUEST,
    _lead_and_writer_task,
    _saved_claim,
    task_by_role,
)


def fake_harvest(queries, platforms=None, limit_per_query=5, community=None) -> Dict[str, Any]:
    return {"count": 0, "items": [], "diagnostics": {}}


def with_tools(engine, **tools):
    registry = engine.toolbox.tools()
    for name, fn in tools.items():
        registry[name] = _def_from(name, fn)


EMPTY_RESULT = {
    "summary": "One search ran and nothing came back.",
    "claims": [],
    "data": {"nothing_found": True, "reason": "One query set returned zero open threads."},
}


def empty_scout_round(engine, scout_id):
    out = engine.call_tool(scout_id, "reach_harvest_threads", {"queries": ["client paid me late again"]})
    assert out["ok"]
    result = {**EMPTY_RESULT, "claims": [{"text": "The harvest returned no threads", "evidence_ids": [out["evidence_id"]]}]}
    return engine.submit_result(scout_id, result)


# ── Honest empty results ──

def test_empty_search_widens_once_then_skips_downstream_work(make_engine, profile):
    engine = make_engine()
    with_tools(engine, reach_harvest_threads=fake_harvest)
    d = engine.open_directive("find me more leads")["directive_id"]
    scout = task_by_role(engine, d, "scout")
    engine.work_order(task_id=scout.id)

    first = empty_scout_round(engine, scout.id)
    assert not first["accepted"] and first["task_status"] == "running" and "widen" in first["issues"][0]
    assert engine.store.get_task(scout.id).attempts == 0  # the CEO's replan does not use an attempt

    second = empty_scout_round(engine, scout.id)
    assert second["accepted"] and second["task_status"] == "done"
    statuses = {t.role: t.status for t in engine.store.list_tasks(d)}
    assert statuses["qualifier"] == statuses["writer"] == statuses["editor"] == statuses["inspector"] == "skipped"
    assert engine.store.get_directive(d).status == "completed"

    report = engine.report(d)
    assert report["headline"].startswith("The search found no open threads")
    assert report["what_was_tried"] and "client paid me late again" in report["what_was_tried"][0]
    assert any("Widen the target" in a for a in report["owner_actions"])
    assert report["quality"]["tasks_skipped_for_empty_input"] == 4
    assert engine.next_step(d)["do"] == "report"


def test_a_scout_that_lists_threads_from_nowhere_is_rejected(make_engine, profile):
    engine = make_engine()
    with_tools(engine, reach_harvest_threads=lambda queries: {"count": 1, "items": [{"url": "https://www.reddit.com/r/a/comments/1/x/"}]})
    d = engine.open_directive("find me more leads")["directive_id"]
    scout = task_by_role(engine, d, "scout")
    out = engine.call_tool(scout.id, "reach_harvest_threads", {"queries": ["late invoices"]})
    result = {
        "summary": "One thread found.",
        "claims": [{"text": "The harvest returned one thread", "evidence_ids": [out["evidence_id"]]}],
        "data": {"threads": [{"url": "https://www.reddit.com/r/made/comments/zzz/up/", "why": "fits"}]},
    }
    verdict = engine.submit_result(scout.id, result)
    assert not verdict["accepted"] and any("not in any harvest result" in i or "URL not found" in i for i in verdict["issues"])


# ── Planning ──

def test_request_without_a_site_makes_the_ceo_ask_the_owner_first(make_engine):
    engine = make_engine()
    opened = engine.open_directive("find customers", intent="find_customers")
    first = opened["tasks"][0]
    assert first["role"] == "owner" and first["status"] == "needs_owner" and opened["status"] == "waiting_owner"
    d = opened["directive_id"]
    step = engine.next_step(d)
    assert step["do"] == "ask_owner" and step["checkpoint"] == "provide_info" and "website" in step["question"]
    assert "error" in engine.resolve_checkpoint(first["task_id"], "reject", "no")
    done = engine.resolve_checkpoint(first["task_id"], "approve", "It is https://tidewatch.example, invoices for freelancers")
    assert done["directive_status"] == "open"
    assert "tidewatch.example" in engine.store.get_directive(d).request
    assert task_by_role(engine, d, "analyst").status == "ready"


def test_custom_request_is_planned_by_rules_without_a_model(make_engine):
    engine = make_engine()
    opened = engine.open_directive("Tell me something useful about my community results", intent="custom")
    roles = [t["role"] for t in opened["tasks"]]
    assert roles == ["strategist"] and any("by rules" in n for n in opened["notes"])
    assert opened["tasks"][0]["status"] == "ready"


def test_custom_request_is_planned_by_the_model_and_validated(make_engine):
    plan = {"tasks": [
        {"key": "a", "role": "researcher", "title": "Read the competitor page", "instruction": "Fetch it.", "depends_on": []},
        {"key": "b", "role": "strategist", "title": "Compare", "instruction": "Compare.", "depends_on": ["a"]},
    ]}
    engine = make_engine(FakeLLM([{"intent": "custom"}, plan]))
    opened = engine.open_directive("Compare our pricing with https://rival.example pricing page please and rank us")
    roles = [t["role"] for t in opened["tasks"]]
    assert roles == ["researcher", "strategist"] and any("by model" in n for n in opened["notes"])

    bad = {"tasks": [{"key": "a", "role": "inspector", "title": "x"}]}
    engine = make_engine(FakeLLM([{"intent": "custom"}, bad]))
    opened = engine.open_directive("Something unusual about my account health this month")
    assert [t["role"] for t in opened["tasks"]] == ["strategist"] and any("by rules" in n for n in opened["notes"])


def test_new_intents_route_to_new_playbooks(make_engine):
    engine = make_engine()
    assert engine.open_directive("research the competitors of Tidewatch")["playbook"] == "market_research"
    assert engine.open_directive("did anyone reply to my posted comments? follow up")["playbook"] == "follow_up"
    assert engine.open_directive("review my drafts before I post")["playbook"] == "review_drafts"
    assert engine.open_directive("weekly review please")["playbook"] == "weekly_review"


def test_the_same_open_request_is_not_planned_twice(make_engine):
    engine = make_engine()
    first = engine.open_directive(REQUEST)
    again = engine.open_directive(REQUEST)
    assert again["directive_id"] == first["directive_id"] and again["duplicate"] is True
    assert len(engine.store.list_directives(10)) == 1


def test_open_directive_reports_what_the_company_lacks(make_engine):
    engine = make_engine()
    notes = " ".join(engine.open_directive(REQUEST)["readiness"]["notes"])
    assert "No server model key" in notes and "No account is linked" in notes and "voice samples" in notes


# ── next_step, cancel, budget, recovery ──

def test_next_step_walks_the_host_through_the_plan(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    step = engine.next_step(d)
    assert step["do"] == "work" and step["role"] == "analyst" and step["progress"] == {"done": 0, "total": 7}
    analyst = task_by_role(engine, d, "analyst")
    for _ in range(3):
        engine.call_tool(analyst.id, "reach_get_or_create_profile", {})  # bad calls: the task escalates after 3 rejections
        engine.submit_result(analyst.id, {"summary": "x"})
    step = engine.next_step(d)
    assert step["do"] == "decide" and "ceo_update_task" in step["choices"][0]


def test_next_step_tells_a_server_with_a_model_to_run(make_engine):
    engine = make_engine(FakeLLM([]))
    d = engine.open_directive(REQUEST, intent="find_customers")["directive_id"]
    assert engine.next_step(d)["do"] == "run"


def test_cancel_stops_every_open_task_and_blocks_tools(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    analyst = task_by_role(engine, d, "analyst")
    out = engine.cancel_directive(d, "changed my mind")
    assert out["status"] == "cancelled" and out["tasks_stopped"] == 7
    assert engine.call_tool(analyst.id, "reach_fetch_site_text", {"url": "https://tidewatch.example"})["ok"] is False
    assert engine.next_step(d)["do"] == "stop" and "error" in engine.cancel_directive(d)
    assert "cancelled" in engine.report(d)["headline"]


def test_tool_budget_stops_a_runaway_specialist(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    directive = engine.store.get_directive(d)
    directive.tool_budget = 1
    engine.store.save_directive(directive)
    analyst = task_by_role(engine, d, "analyst")
    assert engine.call_tool(analyst.id, "reach_fetch_site_text", {"url": "https://tidewatch.example"})["ok"]
    blocked = engine.call_tool(analyst.id, "reach_fetch_site_text", {"url": "https://tidewatch.example"})
    assert not blocked["ok"] and "budget" in blocked["error"]


def test_a_task_nobody_finishes_goes_back_to_the_queue(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    analyst = task_by_role(engine, d, "analyst")
    engine.work_order(task_id=analyst.id)
    assert engine.store.get_task(analyst.id).status == "running"
    assert engine.recover_stalled(d) == []  # still inside the lease
    stale = engine.store.get_task(analyst.id)
    stale.started_at = time.time() - 3 * 3600
    engine.store.save_task(stale)
    assert engine.recover_stalled(d) == [analyst.id]
    fresh = engine.store.get_task(analyst.id)
    assert fresh.status == "ready" and "stopped" in fresh.feedback[-1]


def test_evidence_ids_stay_unique_under_parallel_calls(make_engine):
    import threading

    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    analyst = task_by_role(engine, d, "analyst")
    seen = []

    def call():
        seen.append(engine.call_tool(analyst.id, "reach_fetch_site_text", {"url": "https://tidewatch.example"})["evidence_id"])

    threads = [threading.Thread(target=call) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(set(seen)) == 6


# ── Memory ──

def test_owner_preferences_reach_every_work_order_but_never_count_as_evidence(make_engine):
    engine = make_engine()
    assert "error" in engine.remember("short")
    assert engine.remember("Never mention pricing in a first reply.")["remembered"]
    d = engine.open_directive(REQUEST)["directive_id"]
    order = engine.work_order(directive_id=d)
    assert any("Never mention pricing" in m for m in order["work_order"]["company_memory"])
    analyst = task_by_role(engine, d, "analyst")
    got = engine.call_tool(analyst.id, "reach_fetch_site_text", {"url": "https://tidewatch.example"})
    claim = {"text": "Never mention pricing in a first reply", "evidence_ids": ["MEM1"]}
    out = engine.submit_result(analyst.id, {"summary": "Read the site.", "claims": [claim, {"text": "The site loaded", "evidence_ids": [got["evidence_id"]]}], "data": {}})
    assert not out["accepted"] and any("unknown evidence" in i for i in out["issues"])
    memory_id = engine.recall()["memories"][0]["id"]
    assert engine.forget(memory_id)["forgotten"] and engine.recall()["memories"] == []


def test_a_rejected_checkpoint_teaches_the_company(make_engine, profile):
    engine = make_engine()
    d = engine.open_directive("find customers for https://other.example")["directive_id"]
    cp = next(t for t in engine.store.list_tasks(d) if t.kind == "checkpoint")
    cp.status = "needs_owner"
    engine.store.save_task(cp)
    engine.resolve_checkpoint(cp.id, "reject", "Aim at agencies, not freelancers")
    kinds = {(m["kind"], m["text"]) for m in engine.recall()["memories"]}
    assert any(k == "owner_preference" and "agencies" in t for k, t in kinds)


def test_checkpoint_answers_record_which_channel_gave_them(make_engine):
    engine = make_engine()
    d = engine.open_directive("find customers", intent="find_customers")["directive_id"]
    cp = next(t for t in engine.store.list_tasks(d) if t.kind == "checkpoint")
    engine.resolve_checkpoint(cp.id, "approve", "It is https://tidewatch.example", via="dashboard")
    assert engine.report(d)["owner_confirmations"][0] == {"checkpoint": "provide_info", "via": "dashboard", "message": "It is https://tidewatch.example"}


# ── The editor loop ──

def _editor_setup(engine, storage, thread):
    d, lead_id, wr = _lead_and_writer_task(engine, storage, thread)
    saved = engine.call_tool(wr, "reach_save_reply", {"lead_id": lead_id, "value_first": GOOD_REPLY.replace("Past 30 days", "Past a month")})
    reply_id = saved["result"]["reply_id"]
    assert engine.submit_result(wr, {"summary": "Drafted one reply.", "claims": [_saved_claim(saved)], "data": {"reply_ids": [reply_id]}})["accepted"]
    ed = engine.create_task(d, "editor", "Second read", "Read it.", depends_on=[wr])["task"]["task_id"]
    cp = engine.create_task(d, "inspector", "Inspect the gates", "Run.", depends_on=[ed])["task"]["task_id"]
    return d, lead_id, reply_id, ed, cp


def _review(engine, ed, reply_id, verdict, reasons):
    read = engine.call_tool(ed, "team_read_replies", {})
    engine.call_tool(ed, "reach_lint_reply", {"text": GOOD_REPLY.replace("Past 30 days", "Past a month")})
    return engine.submit_result(ed, {
        "summary": "Read the draft.",
        "claims": [{"text": "The draft was read", "evidence_ids": [read["evidence_id"]]}],
        "data": {"reviews": [{"reply_id": reply_id, "verdict": verdict, "reasons": reasons}]},
    })


def test_editor_revise_sends_the_draft_back_once_and_holds_the_inspection(make_engine, storage, profile, thread):
    engine = make_engine()
    d, lead_id, reply_id, ed, cp = _editor_setup(engine, storage, thread)
    out = _review(engine, ed, reply_id, "revise", ["Does not answer the question about reminders in the thread"])
    assert out["accepted"], out
    tasks = engine.store.list_tasks(d)
    rewrite = next(t for t in tasks if t.role == "writer" and t.round == 1)
    again = next(t for t in tasks if t.role == "editor" and t.round == 1)
    assert "reminders" in rewrite.instruction and again.depends_on == [rewrite.id]
    assert engine.store.get_task(cp).status == "pending" and again.id in engine.store.get_task(cp).depends_on
    assert any("revises once" in n for n in engine.store.get_directive(d).notes)
    assert any(m["kind"] == "lesson" and "editor" in m["text"] for m in engine.recall()["memories"])


def test_editor_reject_retires_the_draft(make_engine, storage, profile, thread):
    engine = make_engine()
    d, lead_id, reply_id, ed, cp = _editor_setup(engine, storage, thread)
    assert _review(engine, ed, reply_id, "reject", ["Pitches the product to someone who asked for advice only"])["accepted"]
    assert storage.get_reply(reply_id).status == "rejected"


def test_editor_must_review_every_new_draft_and_give_reasons(make_engine, storage, profile, thread):
    engine = make_engine()
    d, lead_id, reply_id, ed, cp = _editor_setup(engine, storage, thread)
    out = _review(engine, ed, reply_id, "revise", [])
    assert not out["accepted"] and "concrete reason" in " ".join(out["issues"])
    read = engine.call_tool(ed, "team_read_replies", {})
    none = engine.submit_result(ed, {
        "summary": "Read the draft.", "claims": [{"text": "The draft was read", "evidence_ids": [read["evidence_id"]]}],
        "data": {"reviews": []},
    })
    assert not none["accepted"] and "no review" in " ".join(none["issues"])


# ── New members: researcher and follow-up ──

def test_researcher_facts_need_a_quote_from_a_page_fetched_in_the_task(make_engine):
    engine = make_engine()
    d = engine.open_directive("research the competitors of Tidewatch, see https://tidewatch.example")["directive_id"]
    researcher = task_by_role(engine, d, "researcher")
    fetched = engine.call_tool(researcher.id, "reach_fetch_site_text", {"url": "https://tidewatch.example"})
    claim = {"text": "The site lists a price of 12 dollars per month", "evidence_ids": [fetched["evidence_id"]]}
    out = engine.submit_result(researcher.id, {"summary": "Read the pricing line.", "claims": [claim], "data": {"sources": ["https://tidewatch.example"]}})
    assert not out["accepted"] and "no quote" in " ".join(out["issues"])
    claim["quote"] = "Pricing: 12 dollars per month"
    bad_source = engine.submit_result(researcher.id, {"summary": "Read the pricing line.", "claims": [claim], "data": {"sources": ["https://rival.example"]}})
    assert not bad_source["accepted"] and "not fetched" in " ".join(bad_source["issues"])
    ok = engine.submit_result(researcher.id, {"summary": "Read the pricing line.", "claims": [claim], "data": {"sources": ["https://tidewatch.example"]}})
    assert ok["accepted"], ok


def test_follow_up_reports_only_threads_it_read(make_engine, thread):
    engine = make_engine()
    with_tools(engine, reach_read_thread=lambda url, max_comments=40: {"url": url, "post": {}, "comments": [{"id": "c1", "body": "thanks"}], "targets": [], "warnings": []})
    d = engine.open_directive("follow up on my posted replies")["directive_id"]
    track = task_by_role(engine, d, "follow_up")
    read = engine.call_tool(track.id, "reach_read_thread", {"url": thread.url})
    claim = {"text": "The thread has one comment", "evidence_ids": [read["evidence_id"]]}
    unread = {"summary": "Checked.", "claims": [claim], "data": {"threads": [{"url": "https://www.reddit.com/r/x/comments/9/y/", "state": "open"}]}}
    assert not engine.submit_result(track.id, unread)["accepted"]
    good = {"summary": "Checked.", "claims": [claim], "data": {"threads": [{"url": thread.url, "state": "new_replies", "new_comments": 1}]}}
    assert engine.submit_result(track.id, good)["accepted"]


# ── The worker fixes its own mistakes before an attempt is spent ──

def test_worker_fixes_verifier_issues_inside_one_attempt(make_engine):
    site = "https://tidewatch.example"
    profile_args = {
        "name": "Tidewatch", "url": site, "description": "Invoice tracking for freelancers",
        "features": ["automatic invoice reminders"], "problems_solved": ["late invoices"], "pricing_info": "12 dollars per month",
        "pain_vocabulary": ["client paid me late again", "chasing invoices every month"],
    }
    good_claim = {"text": "Tidewatch tracks invoices for freelancers", "evidence_ids": ["E1"], "quote": "Tidewatch tracks invoices for freelancers"}
    script = [
        {"action": "call_tool", "tool": "reach_fetch_site_text", "args": {"url": site}},
        {"action": "call_tool", "tool": "reach_get_or_create_profile", "args": profile_args},
        {"action": "final", "result": {"summary": "Profile saved.", "claims": [], "data": {}}},  # no claims: the pre-check objects
        {"action": "final", "result": {"summary": "Profile saved.", "claims": [good_claim], "data": {"profile_id": "p"}}},
    ]
    llm = FakeLLM(script)
    engine = make_engine(llm)
    d = engine.open_directive(REQUEST, intent="find_customers")["directive_id"]
    engine.run(d)
    analyst = task_by_role(engine, d, "analyst")
    assert analyst.status == "done" and analyst.attempts == 1
    assert any("verifier_issues" in p for p in llm.prompts)


def test_a_rate_limited_model_does_not_cost_the_specialist_an_attempt(make_engine):
    def busy(prompt):
        raise RuntimeError("provider returned HTTP 429 rate limit")

    llm = FakeLLM([busy, busy, {"action": "call_tool", "tool": "reach_fetch_site_text", "args": {"url": "https://tidewatch.example"}}])
    engine = make_engine(llm)
    engine.backoff_scale = 0
    d = engine.open_directive(REQUEST, intent="find_customers")["directive_id"]
    engine.run(d, max_tasks=1)
    busy_events = [e for e in engine.store.events(d, 50) if e["kind"] == "model_busy"]
    assert len(busy_events) == 2
    # The two busy replies used no attempt. The first attempt that counted is the one that failed after them.
    analyst = task_by_role(engine, d, "analyst")
    assert analyst.attempts >= 1 and analyst.tool_calls >= 1


# ── The report ──

def test_report_shows_lead_cards_trust_and_drafts(make_engine, storage, profile, thread):
    engine = make_engine()
    d, lead_id, reply_id, ed, cp = _editor_setup(engine, storage, thread)
    report = engine.report(d)
    card = next(c for c in report["lead_cards"] if c["lead_id"] == lead_id)
    assert card["quote_verified"] and card["evidence_quote"] and card["reply"]["reply_id"] == reply_id
    assert card["reply"]["lint_passed"] is True and report["trust"] == "partial"
    assert "lead(s) saved" in report["headline"] and report["progress"]["total"] >= 3


def test_inspector_flags_a_draft_edited_after_the_editor_read_it(make_engine, storage, profile, thread):
    import time as _time

    engine = make_engine()
    d, lead_id, reply_id, ed, cp = _editor_setup(engine, storage, thread)
    # Run the editor to approve, which also lets the automatic inspector run once the draft is unchanged.
    assert _review(engine, ed, reply_id, "approve", [])["accepted"]
    assert engine.store.get_task(cp).result["data"]["inspections"][0]["attention"] == []
    # Change the draft later and inspect again with a fresh task.
    _time.sleep(1.2)
    reply = storage.get_reply(reply_id)
    reply.value_first = reply.value_first + " Hope that helps."
    storage.save_reply(reply)
    again = engine.create_task(d, "inspector", "Inspect again", "Run.")["task"]["task_id"]
    row = engine.store.get_task(again).result["data"]["inspections"][0]
    assert not row["ready"] and any("changed after the editor" in a for a in row["attention"])
    assert any("changed after the editor" in a for a in engine.report(d)["owner_actions"])
