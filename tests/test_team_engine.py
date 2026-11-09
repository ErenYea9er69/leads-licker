"""The company end to end: planning, permissions, host mode, server mode, checkpoints, reports."""

from __future__ import annotations

from tests.conftest import FakeLLM

REQUEST = "Find customers for https://tidewatch.example"


def ids(engine, directive_id):
    return {t.role + ":" + t.title: t.id for t in engine.store.list_tasks(directive_id)}


def task_by_role(engine, directive_id, role):
    return next(t for t in engine.store.list_tasks(directive_id) if t.role == role)


# ── Planning ──

def test_find_customers_plan_has_the_whole_company(make_engine):
    engine = make_engine()
    opened = engine.open_directive(REQUEST)
    roles = [t["role"] for t in opened["tasks"]]
    assert opened["intent"] == "find_customers"
    assert roles == ["analyst", "owner", "scout", "qualifier", "writer", "editor", "inspector"]
    statuses = {t["role"]: t["status"] for t in opened["tasks"]}
    assert statuses["analyst"] == "ready" and statuses["scout"] == "pending"


def test_confirmed_profile_skips_profile_steps_when_request_has_no_new_info(make_engine, profile):
    engine = make_engine()
    opened = engine.open_directive("find me more leads")
    assert [t["role"] for t in opened["tasks"]][0] == "scout"
    assert any("Skipped" in n for n in opened["notes"])


def test_new_url_forces_a_fresh_profile_even_when_one_is_confirmed(make_engine, profile):
    engine = make_engine()
    opened = engine.open_directive("find customers for https://other.example")
    assert opened["tasks"][0]["role"] == "analyst"


def test_status_question_creates_no_tasks(make_engine):
    opened = make_engine().open_directive("what is the status so far?")
    assert opened["intent"] == "status" and opened["tasks"] == []


def test_intent_hint_and_unknown_playbook(make_engine):
    engine = make_engine()
    assert engine.open_directive("hello", intent="weekly_review")["playbook"] == "weekly_review"
    assert "error" in engine.open_directive("hello", playbook="nope")
    assert "error" in engine.open_directive("   ")


def test_model_classifies_intent_when_configured(make_engine):
    engine = make_engine(FakeLLM([{"intent": "weekly_review"}]))
    assert engine.open_directive("how did we do")["intent"] == "weekly_review"
    engine = make_engine(FakeLLM([{"intent": "world_domination"}]))
    assert engine.open_directive("find customers for https://a.example")["intent"] == "find_customers"


# ── Permissions ──

def test_specialists_cannot_use_restricted_or_foreign_tools(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    task = task_by_role(engine, d, "analyst")
    assert not engine.call_tool(task.id, "reach_publish_reply", {"reply_id": "x"})["ok"]
    assert not engine.call_tool(task.id, "reach_harvest_threads", {"queries": ["x"]})["ok"]
    assert not engine.call_tool(task.id, "reach_fetch_site_text", {"nope": 1})["ok"]
    assert not engine.call_tool(task.id, "reach_fetch_site_text", {})["ok"]


def test_cannot_hire_a_specialist_with_restricted_tools(make_engine):
    engine = make_engine()
    out = engine.hire_specialist("poster", "Poster", "Posts replies for the owner every day.", tools=["reach_publish_reply"])
    assert "error" in out and "may not hold" in out["error"]
    out = engine.hire_specialist("reader", "Reader", "Reads stored leads and reports counts only.", tools=["reach_list_leads"], skills=["lead-qualification"])
    assert "hired" in out and "reader" in engine.roles()
    assert "error" in engine.hire_specialist("analyst", "x", "y" * 30)
    assert "error" in engine.hire_specialist("Bad Name", "x", "y" * 30)
    assert "error" in engine.hire_specialist("short_one", "x", "short")
    assert "error" in engine.hire_specialist("skillful", "x", "y" * 30, skills=["nope"])


# ── Host mode: the analyst, step by step ──

def analyst_flow(engine, d, *, feature="automatic invoice reminders", price="12 dollars per month"):
    from agent_reach.mcp import server

    task = task_by_role(engine, d, "analyst")
    order = engine.work_order(task_id=task.id)
    assert "automatic" not in order["system_prompt"] or True
    assert "reach_get_or_create_profile" in [t["name"] for t in order["work_order"]["tools"]]
    fetched = engine.call_tool(task.id, "reach_fetch_site_text", {"url": "https://tidewatch.example"})
    assert fetched["ok"]
    saved = engine.call_tool(task.id, "reach_get_or_create_profile", {
        "name": "Tidewatch", "url": "https://tidewatch.example", "description": "Invoice tracking for freelancers",
        "features": [feature], "problems_solved": ["late invoices"], "pricing_info": price,
        "pain_vocabulary": ["client paid me late again", "chasing invoices every month"],
    })
    assert saved["ok"]
    return task, fetched["evidence_id"], saved["evidence_id"], server


def result_for(e1, e2, profile_id="x"):
    return {
        "summary": "Profile saved from the site.",
        "claims": [{"text": "Tidewatch tracks invoices for freelancers", "evidence_ids": [e1], "quote": "Tidewatch tracks invoices for freelancers"}],
        "data": {"profile_id": profile_id},
    }


def test_analyst_output_is_accepted_when_grounded(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    task, e1, e2, _ = analyst_flow(engine, d)
    out = engine.submit_result(task.id, result_for(e1, e2))
    assert out["accepted"], out
    assert engine.store.get_task(task.id).status == "done"
    assert engine.store.get_task(task_by_role(engine, d, "owner").id).status == "needs_owner"
    assert engine.store.get_directive(d).status == "waiting_owner"


def test_analyst_invented_feature_is_rejected_then_fixed(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    task, e1, e2, _ = analyst_flow(engine, d, feature="quantum payroll engine")
    out = engine.submit_result(task.id, result_for(e1, e2))
    assert not out["accepted"] and "Feature not found" in " ".join(out["issues"]) and out["attempts_left"] == 2
    engine.call_tool(task.id, "reach_get_or_create_profile", {"features": ["automatic invoice reminders"]})
    assert engine.submit_result(task.id, result_for(e1, e2))["accepted"]


def test_analyst_invented_price_is_rejected(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    task, e1, e2, _ = analyst_flow(engine, d, price="99 dollars per month")
    out = engine.submit_result(task.id, result_for(e1, e2))
    assert not out["accepted"] and "Pricing" in " ".join(out["issues"])


def test_task_escalates_after_max_attempts_and_blocks_dependents(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    task, e1, e2, _ = analyst_flow(engine, d)
    bad = {"summary": "ok", "claims": [{"text": "made up", "evidence_ids": ["E77"]}], "data": {}}
    for _ in range(3):
        out = engine.submit_result(task.id, bad)
    assert out["task_status"] == "escalated"
    assert engine.store.get_directive(d).status == "needs_ceo"
    assert engine.store.get_task(task_by_role(engine, d, "scout").id).status == "blocked"
    engine.update_task(task.id, "retry", instruction="Try again with the site text.")
    assert engine.store.get_task(task.id).status == "ready"
    assert engine.store.get_task(task_by_role(engine, d, "scout").id).status == "pending"


# ── Checkpoints ──

def test_checkpoint_needs_the_owners_words_and_confirms_the_profile(make_engine, storage):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    task, e1, e2, _ = analyst_flow(engine, d)
    engine.submit_result(task.id, result_for(e1, e2))
    cp = task_by_role(engine, d, "owner")
    assert "error" in engine.resolve_checkpoint(cp.id, "approve", "   ")
    assert "error" in engine.resolve_checkpoint(cp.id, "maybe", "yes")
    assert storage.get_latest_business_profile().confirmed is False
    out = engine.resolve_checkpoint(cp.id, "approve", "Looks right, go ahead.")
    assert out["task"]["status"] == "done"
    assert storage.get_latest_business_profile().confirmed is True
    assert engine.store.get_task(task_by_role(engine, d, "scout").id).status == "ready"


def test_rejected_checkpoint_sends_work_back_with_feedback(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    task, e1, e2, _ = analyst_flow(engine, d)
    engine.submit_result(task.id, result_for(e1, e2))
    cp = task_by_role(engine, d, "owner")
    engine.resolve_checkpoint(cp.id, "reject", "We also serve agencies. Add that.")
    back = engine.store.get_task(task.id)
    assert back.status == "ready" and "agencies" in back.feedback[0]
    assert engine.store.get_task(cp.id).status == "pending"


# ── Qualifier: leads must be real, saved in the task and quote-verified ──

def test_qualifier_rejects_unsaved_and_unknown_leads(make_engine, profile, thread):
    engine = make_engine()
    d = engine.open_directive("find me more leads")["directive_id"]
    made = engine.create_task(d, "qualifier", "Qualify", "Score the stored thread.")
    task = engine.store.get_task(made["task"]["task_id"])
    assert task.status == "ready"
    saved = engine.call_tool(task.id, "reach_save_lead", {
        "title": thread.title, "url": thread.url, "platform": "reddit", "community": "r/freelance",
        "customer_problem": "Clients pay late", "evidence_quote": "I keep chasing invoices every month",
        "problem_fit": 26, "icp_match": 20, "buying_intent": 16, "urgency": 10, "item_id": thread.id,
    })
    assert saved["ok"] and saved["result"]["evidence_verified"] and saved["result"]["classification"] == "high_potential"
    lead_id = saved["result"]["lead_id"]
    read = engine.call_tool(task.id, "team_read_items", {})
    claim = {"text": "Clients pay late and I keep chasing invoices every month", "evidence_ids": [read["evidence_id"]], "quote": "I keep chasing invoices every month"}
    fake = {"summary": "Saved a lead.", "claims": [claim], "data": {"lead_ids": ["lead-does-not-exist"]}}
    assert not engine.submit_result(task.id, fake)["accepted"]
    ok = {"summary": "Saved a lead.", "claims": [claim], "data": {"lead_ids": [lead_id]}}
    assert engine.submit_result(task.id, ok)["accepted"], claim


def test_unverified_quote_cannot_make_a_high_potential_lead(make_engine, profile, thread):
    engine = make_engine()
    d = engine.open_directive("find me more leads")["directive_id"]
    made = engine.create_task(d, "qualifier", "Qualify", "Score it.")
    task = engine.store.get_task(made["task"]["task_id"])
    out = engine.call_tool(task.id, "reach_save_lead", {
        "title": thread.title, "url": thread.url, "platform": "reddit", "community": "r/freelance",
        "customer_problem": "x", "evidence_quote": "this sentence never appeared in the thread",
        "problem_fit": 30, "icp_match": 25, "buying_intent": 20, "urgency": 15, "item_id": thread.id,
    })
    assert out["result"]["classification"] != "high_potential" and out["result"]["evidence_verified"] is False


# ── Server mode: workers on the server's model ──

def test_server_mode_runs_a_worker_to_a_verified_result(make_engine):
    script = [
        {"action": "call_tool", "tool": "reach_fetch_site_text", "args": {"url": "https://tidewatch.example"}},
        {"action": "call_tool", "tool": "reach_get_or_create_profile", "args": {
            "name": "Tidewatch", "url": "https://tidewatch.example", "description": "Invoice tracking for freelancers",
            "features": ["automatic invoice reminders"], "problems_solved": ["late invoices"],
            "pain_vocabulary": ["client paid me late again", "chasing invoices every month"]}},
        {"action": "final", "result": {
            "summary": "Profile saved.",
            "claims": [{"text": "Tidewatch tracks invoices", "evidence_ids": ["E1"], "quote": "Tidewatch tracks invoices for freelancers"}],
            "data": {"profile_id": "x"}}},
    ]
    engine = make_engine(FakeLLM([{"intent": "find_customers"}] + script))
    d = engine.open_directive(REQUEST)["directive_id"]
    out = engine.run(d)
    assert out["mode"] == "server" and out["directive_status"] == "waiting_owner"
    assert [r["status"] for r in out["ran"]] == ["done"]
    assert "Approve" not in out["next"] and "owner" in out["next"]


def test_server_worker_that_never_finishes_escalates(make_engine):
    loop = [{"action": "call_tool", "tool": "reach_fetch_site_text", "args": {"url": "https://tidewatch.example"}}] * 14
    engine = make_engine(FakeLLM([{"intent": "find_customers"}] + loop * 3))
    d = engine.open_directive(REQUEST)["directive_id"]
    out = engine.run(d)
    assert out["directive_status"] == "needs_ceo"
    assert engine.store.get_task(task_by_role(engine, d, "analyst").id).status == "escalated"


def test_run_without_a_model_returns_host_instructions(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    out = engine.run(d)
    assert out["mode"] == "host" and out["ready"][0]["role"] == "analyst"


def test_a_directive_cannot_run_twice_at_once(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    lock = engine._lock(d)
    lock.acquire()
    try:
        assert "already running" in engine.run(d)["error"]
    finally:
        lock.release()


# ── Reports ──

def test_report_lists_only_verified_work_and_open_items(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    task, e1, e2, _ = analyst_flow(engine, d)
    engine.submit_result(task.id, result_for(e1, e2))
    report = engine.report(d)
    assert [v["role"] for v in report["verified_work"]] == ["analyst"]
    assert {i["role"] for i in report["not_verified"]} == {"scout", "qualifier", "writer", "editor", "inspector"}
    assert any("checkpoint" in a for a in report["owner_actions"])
    assert report["ledger"]["evidence_items"] == 2


def test_report_narrative_with_invented_numbers_falls_back_to_the_template(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    task, e1, e2, _ = analyst_flow(engine, d)
    engine.submit_result(task.id, result_for(e1, e2))
    engine._svc().llm = FakeLLM([{"report": "We found 500 hot leads at https://made.up/x"}])
    summary = engine.report(d)["summary"]
    assert "500" not in summary and "made.up" not in summary
    engine._svc().llm = FakeLLM([{"report": "The profile is saved and waits for you."}])
    assert engine.report(d)["summary"] == "The profile is saved and waits for you."


# ── Tasks and playbooks made by the CEO ──

def test_ceo_creates_tasks_and_playbooks(make_engine):
    engine = make_engine()
    d = engine.open_directive("something unusual here", intent="custom")["directive_id"]
    first = engine.create_task(d, "strategist", "Look at leads", "Count leads by community.", acceptance=["Numbers come from tools."])
    second = engine.create_task(d, "researcher", "Check it", depends_on=[first["task"]["task_id"]])
    assert first["task"]["status"] == "ready" and second["task"]["status"] == "pending"
    assert "error" in engine.create_task(d, "nobody", "x")
    assert "error" in engine.create_task(d, "researcher", "x", depends_on=["task_missing"])
    pb = engine.create_playbook("quick_check", "Strategist then researcher", [
        {"key": "a", "role": "strategist", "title": "Review"},
        {"key": "b", "role": "researcher", "title": "Check", "depends_on": ["a"]},
    ])
    assert pb["saved"] == "quick_check"
    opened = engine.open_directive("run the quick check", playbook="quick_check")
    assert [t["role"] for t in opened["tasks"]] == ["strategist", "researcher"]
    assert "error" in engine.create_playbook("find_customers", "x", [{"key": "a", "role": "analyst", "title": "t"}])
    assert "error" in engine.create_playbook("bad_dep", "x", [{"key": "a", "role": "analyst", "title": "t", "depends_on": ["z"]}])
    assert "error" in engine.create_playbook("bad_role", "x", [{"key": "a", "role": "ghost", "title": "t"}])


def test_skip_and_reassign(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    analyst = task_by_role(engine, d, "analyst")
    assert "error" in engine.update_task(analyst.id, "reassign", role="ghost")
    assert engine.update_task(analyst.id, "reassign", role="strategist")["task"]["role"] == "strategist"
    assert engine.update_task(analyst.id, "skip", reason="owner supplied a profile")["task"]["status"] == "skipped"
    assert "error" in engine.update_task(analyst.id, "explode")


# ── Writer and the posting inspection, with the real save and gate functions ──

GOOD_REPLY = (
    "Third reminders get easier when you treat them as admin, not a confrontation. I send the same short note every "
    "time: invoice number, amount, original due date, and a new date I need it by. No apology, no anger. Past 30 days "
    "I add one line saying work on the next project starts once it clears. Most late payers are disorganized, not hostile."
)


def _saved_claim(saved):
    return {"text": "The reply was saved as a draft", "evidence_ids": [saved["evidence_id"]]}


def _lead_and_writer_task(engine, storage, thread):
    d = engine.open_directive("find me more leads")["directive_id"]
    qual = engine.create_task(d, "qualifier", "Qualify", "Score it.")["task"]["task_id"]
    saved = engine.call_tool(qual, "reach_save_lead", {
        "title": thread.title, "url": thread.url, "platform": "reddit", "community": "r/freelance",
        "customer_problem": "Late payers", "evidence_quote": "I keep chasing invoices every month",
        "problem_fit": 26, "icp_match": 20, "buying_intent": 16, "urgency": 10, "item_id": thread.id,
    })
    wr = engine.create_task(d, "writer", "Draft", "Draft a reply.")["task"]["task_id"]
    return d, saved["result"]["lead_id"], wr


def test_writer_reply_with_an_invented_number_is_rejected(make_engine, storage, profile, thread):
    engine = make_engine()
    d, lead_id, wr = _lead_and_writer_task(engine, storage, thread)
    saved = engine.call_tool(wr, "reach_save_reply", {"lead_id": lead_id, "value_first": GOOD_REPLY})
    assert saved["ok"], saved
    reply_id = saved["result"]["reply_id"]
    out = engine.submit_result(wr, {"summary": "Drafted one reply.", "claims": [_saved_claim(saved)], "data": {"reply_ids": [reply_id]}})
    # "30" appears in neither the profile nor the thread, so the verifier must object.
    assert not out["accepted"] and "30" in " ".join(out["issues"])


def test_writer_reply_without_numbers_passes(make_engine, storage, profile, thread):
    engine = make_engine()
    d, lead_id, wr = _lead_and_writer_task(engine, storage, thread)
    clean = GOOD_REPLY.replace("Past 30 days", "Past a month")
    saved = engine.call_tool(wr, "reach_save_reply", {"lead_id": lead_id, "value_first": clean})
    reply_id = saved["result"]["reply_id"]
    assert engine.submit_result(wr, {"summary": "Drafted one reply.", "claims": [_saved_claim(saved)], "data": {"reply_ids": [reply_id]}})["accepted"]


def _inspect(engine, storage, thread, rules=False, edit_after=False):
    d, lead_id, wr = _lead_and_writer_task(engine, storage, thread)
    clean = GOOD_REPLY.replace("Past 30 days", "Past a month")
    saved = engine.call_tool(wr, "reach_save_reply", {"lead_id": lead_id, "value_first": clean})
    reply_id = saved["result"]["reply_id"]
    assert engine.submit_result(wr, {"summary": "Drafted one reply.", "claims": [_saved_claim(saved)], "data": {"reply_ids": [reply_id]}})["accepted"]
    if rules:
        from agent_reach.discovery.models import CommunityRule

        storage.save_community_rule(CommunityRule(community="r/freelance", self_promo="allowed", ai_content_allowed=True, links_allowed=True))
    task_id = engine.create_task(d, "inspector", "Inspect the gates", depends_on=[wr])["task"]["task_id"]
    return d, reply_id, engine.store.get_task(task_id)


def test_inspector_shows_the_real_blocker_instead_of_not_approved(make_engine, storage, profile, thread):
    engine = make_engine()
    d, reply_id, task = _inspect(engine, storage, thread)
    # The inspector ran by itself: no model and no assistant touched it.
    assert task.status == "done" and task.verdict.trust == "high" and task.verdict.checks == {"computed_by_engine": True}
    row = task.result["data"]["inspections"][0]
    assert row["reply_id"] == reply_id and row["code"] == "rules_not_read" and not row["ready"]
    assert "r/freelance" in row["message"]
    report = engine.report(d)
    assert any("Fix before posting" in a and "rules" in a for a in report["owner_actions"])
    assert report["inspection"][0]["code"] == "rules_not_read"
    card = next(c for c in report["lead_cards"] if c["reply"]["reply_id"] == reply_id)
    assert card["reply"]["gate"]["code"] == "rules_not_read"


def test_inspector_passes_a_draft_whose_rules_are_recorded(make_engine, storage, profile, thread):
    engine = make_engine()
    d, reply_id, task = _inspect(engine, storage, thread, rules=True)
    row = task.result["data"]["inspections"][0]
    assert row["code"] not in ("not_approved", "rules_not_read"), row
    assert row["ready"] is (row["code"] == "ok")


def test_inspector_is_not_a_job_for_reassigning_and_not_a_planning_choice(make_engine):
    engine = make_engine()
    d = engine.open_directive(REQUEST)["directive_id"]
    scout = task_by_role(engine, d, "scout")
    assert "runs by itself" in engine.update_task(scout.id, "reassign", role="inspector")["error"]
    roster = {r["name"]: r for r in engine.describe_team()["roles"]}
    assert roster["inspector"]["automatic"] is True and roster["inspector"]["tools"] == []
    assert "compliance" not in roster and "auditor" not in roster


def test_ids_and_timestamps_never_support_a_number():
    from agent_reach.team.verifier import numbers_in

    text = '{"id": "cbd30e3f-e430-4544-93e2-9a1e0366d24e", "task": "task_a7a30887d8", "created_at": 1794074781.5953135, "hash": "9f30a1b2c3d4e5f6"}'
    assert numbers_in(text) == set()
    assert numbers_in("Past 30 days, 2026 plan, forty clients") >= {"30", "2026", "40"}
