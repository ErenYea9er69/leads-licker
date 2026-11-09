"""The verifier is the anti-hallucination gate. These tests feed it bad output on purpose."""

from __future__ import annotations

from agent_reach.team.models import Directive, Evidence, RoleSpec, Task
from agent_reach.team.roles import BUILTIN_ROLES
from agent_reach.team.verifier import Verifier, numbers_in, urls_in


def _setup(svc, request="Find customers for https://tidewatch.example"):
    d = Directive(request=request)
    t = Task(directive_id=d.id, role="scout", title="t")
    ev = Evidence(id="E1", tool="reach_harvest_threads", text='{"count": 12, "items": [{"url": "https://www.reddit.com/r/x/comments/1/a/"}]}')
    t.evidence = [ev]  # the task made the call, so it did real work
    return Verifier(lambda: svc, audit=False), d, t, [ev]


def good(**over):
    base = {"summary": "Found threads.", "claims": [{"text": "Harvest returned 12 threads", "evidence_ids": ["E1"]}], "data": {}}
    base.update(over)
    return base


def test_helpers():
    assert numbers_in("pays 1,200 dollars and 5 times 3.5") == {"1200", "3.5"}
    assert urls_in("see https://a.com/x, and (https://b.com).") == ["https://a.com/x", "https://b.com"]


def test_accepts_grounded_output(svc):
    v, d, t, ledger = _setup(svc)
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(), ledger)
    assert verdict.passed, verdict.issues


def test_rejects_non_object_and_missing_summary(svc):
    v, d, t, ledger = _setup(svc)
    assert not v.verify(t, BUILTIN_ROLES["strategist"], d, "text", ledger).passed
    assert not v.verify(t, BUILTIN_ROLES["strategist"], d, {"claims": []}, ledger).passed


def test_rejects_unknown_evidence_id(svc):
    v, d, t, ledger = _setup(svc)
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=[{"text": "x", "evidence_ids": ["E9"]}]), ledger)
    assert not verdict.passed and "unknown evidence" in verdict.issues[0]


def test_rejects_claim_without_evidence_unless_assumption(svc):
    v, d, t, ledger = _setup(svc)
    assert not v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=[{"text": "x"}]), ledger).passed
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=[{"text": "x", "assumption": True}]), ledger)
    assert verdict.passed and verdict.notes


def test_rejects_invented_number(svc):
    v, d, t, ledger = _setup(svc)
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=[{"text": "Harvest returned 40 threads", "evidence_ids": ["E1"]}]), ledger)
    assert not verdict.passed and "40" in verdict.issues[0]


def test_rejects_invented_number_in_summary(svc):
    v, d, t, ledger = _setup(svc)
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(summary="Conversion will reach 85 percent."), ledger)
    assert not verdict.passed


def test_rejects_quote_not_in_evidence(svc):
    v, d, t, ledger = _setup(svc)
    claims = [{"text": "Harvest returned 12 threads", "evidence_ids": ["E1"], "quote": "twelve glorious threads"}]
    assert not v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=claims), ledger).passed
    claims[0]["quote"] = '{"count": 12, "items"'
    assert v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=claims), ledger).passed


def test_rejects_invented_url_but_accepts_request_and_harvested_urls(svc, thread):
    v, d, t, ledger = _setup(svc)
    bad = good(data={"threads": [{"url": "https://www.reddit.com/r/made/comments/zzz/up/"}]})
    assert not v.verify(t, BUILTIN_ROLES["strategist"], d, bad, ledger).passed
    from_request = good(data={"site": "https://tidewatch.example"})
    assert v.verify(t, BUILTIN_ROLES["strategist"], d, from_request, ledger).passed
    stored = good(data={"threads": [{"url": thread.url}]})
    assert v.verify(t, BUILTIN_ROLES["strategist"], d, stored, ledger).passed


def test_scout_needs_a_harvest_call(svc):
    v, d, t, ledger = _setup(svc)
    t.evidence = []
    verdict = v.verify(t, BUILTIN_ROLES["scout"], d, good(), ledger)
    assert not verdict.passed and "harvest" in " ".join(verdict.issues)
    t.evidence = list(ledger)
    assert v.verify(t, BUILTIN_ROLES["scout"], d, good(), ledger).passed


def test_auditor_objection_must_point_at_a_real_claim(svc):
    from tests.conftest import FakeLLM

    v, d, t, ledger = _setup(svc)
    v.audit = True
    # Index 1 is the planted canary. An objection to index 99 points at nothing and is ignored.
    svc.llm = FakeLLM([{"verdict": "fail", "unsupported": [{"n": 99, "reason": "invented"}, {"n": 1, "reason": "canary"}]}])
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(), ledger)
    assert verdict.passed and verdict.auditor == "pass" and verdict.trust == "high"
    svc.llm = FakeLLM([{"verdict": "fail", "unsupported": [{"n": 0, "reason": "overreach"}, {"n": 1, "reason": "canary"}]}])
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(), ledger)
    assert not verdict.passed and verdict.auditor == "fail"


def test_an_auditor_that_passes_the_planted_false_claim_is_marked_unreliable(svc):
    from tests.conftest import FakeLLM

    v, d, t, ledger = _setup(svc)
    v.audit = True
    svc.llm = FakeLLM([{"verdict": "pass", "unsupported": []}])
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(), ledger)
    assert verdict.auditor == "unreliable" and verdict.trust == "low"
    assert any("unreliable" in n for n in verdict.notes)


def test_custom_role_gets_generic_checks_only(svc):
    v, d, t, ledger = _setup(svc)
    role = RoleSpec(name="custom_one", title="C", charter="x" * 30, builtin=False)
    assert v.verify(t, role, d, good(), ledger).passed


# ── Grounding added in 3.1: wording, empty claims, failed calls, spelled numbers ──

def test_claim_with_a_real_quote_but_unrelated_words_is_rejected(svc):
    v, d, t, ledger = _setup(svc)
    claims = [{"text": "Banks worldwide use this product daily", "evidence_ids": ["E1"], "quote": '{"count": 12, "items"'}]
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=claims), ledger)
    assert not verdict.passed and not verdict.checks["support"]


def test_summary_and_no_claims_is_not_work(svc):
    v, d, t, ledger = _setup(svc)
    t.evidence = []
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, {"summary": "Customers love the product.", "claims": [], "data": {}}, ledger)
    assert not verdict.passed and not verdict.checks["work"]


def test_summary_that_says_more_than_the_evidence_is_rejected(svc):
    v, d, t, ledger = _setup(svc)
    summary = "Competitors collapsed because investors panicked about regulation overseas."
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(summary=summary), ledger)
    assert not verdict.passed and not verdict.checks["summary"]


def test_claim_that_cites_only_a_failed_call_is_rejected_unless_it_reports_the_failure(svc):
    v, d, t, ledger = _setup(svc)
    failed = Evidence(id="E2", tool="reach_harvest_threads", ok=False, text='"Search backend timed out for these queries"')
    t.evidence.append(failed)
    ledger.append(failed)
    claims = [{"text": "Search backend timed out", "evidence_ids": ["E2"]}]
    assert not v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=claims), ledger).passed
    claims[0]["about_failure"] = True
    assert v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=claims), ledger).passed


def test_spelled_numbers_are_checked_like_digits(svc):
    assert numbers_in("about forty customers and two hundred") == {"40", "100"}
    v, d, t, ledger = _setup(svc)
    claims = [{"text": "Harvest returned forty threads", "evidence_ids": ["E1"]}]
    verdict = v.verify(t, BUILTIN_ROLES["strategist"], d, good(claims=claims), ledger)
    assert not verdict.passed and not verdict.checks["evidence"]


def test_nothing_found_needs_proof_and_a_reason(svc):
    v, d, t, ledger = _setup(svc)
    empty_ev = Evidence(id="E1", tool="reach_harvest_threads", text='{"count": 0, "items": []}')
    t.evidence = [empty_ev]
    ok = {"summary": "One search ran and nothing came back.", "claims": [{"text": "The harvest returned no threads", "evidence_ids": ["E1"]}],
          "data": {"nothing_found": True, "reason": "One query set returned zero open threads."}}
    assert v.verify(t, BUILTIN_ROLES["scout"], d, ok, [empty_ev]).passed
    no_reason = {**ok, "data": {"nothing_found": True}}
    assert not v.verify(t, BUILTIN_ROLES["scout"], d, no_reason, [empty_ev]).passed
    # A harvest that returned threads makes nothing_found false.
    full = Evidence(id="E1", tool="reach_harvest_threads", text='{"count": 12, "items": []}')
    t.evidence = [full]
    assert not v.verify(t, BUILTIN_ROLES["scout"], d, ok, [full]).passed


def test_scout_must_declare_an_empty_harvest(svc):
    v, d, t, ledger = _setup(svc)
    empty_ev = Evidence(id="E1", tool="reach_harvest_threads", text='{"count": 0, "items": []}')
    t.evidence = [empty_ev]
    result = good(claims=[{"text": "The harvest returned no threads", "evidence_ids": ["E1"]}])
    verdict = v.verify(t, BUILTIN_ROLES["scout"], d, result, [empty_ev])
    assert not verdict.passed and "nothing_found" in " ".join(verdict.issues)
