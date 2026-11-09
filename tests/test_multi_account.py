"""Several accounts per platform and several replies per thread."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from agent_reach.discovery import thread_rules
from agent_reach.discovery.accounts import AccountError, AccountService, account_key
from agent_reach.discovery.models import (
    GeneratedReply,
    LeadQualification,
    PostingSettings,
    ScoreBreakdown,
)
from agent_reach.discovery.publisher import CommunityPublisher
from agent_reach.discovery.reply_generator import ReplyGenerationError
from agent_reach.discovery.storage import DiscoveryStorage

URL = "https://www.reddit.com/r/freelance/comments/abc123/late_invoices/"


LONG = "Reminders after day five work better than one monthly email, and most freelancers I know switched to that rhythm."
LONG2 = "Net 15 terms help more than any reminder does, since clients read the due date on day one and plan around it."


def make_lead(storage: DiscoveryStorage, url: str = URL, lead_id: str = "L1") -> LeadQualification:
    lead = LeadQualification(
        id=lead_id, discovered_item_id="i1", title="Late invoices", url=url, platform="reddit", community="r/freelance",
        author="op", published_at="2026-11-01", excerpt="clients pay late", customer_problem="late invoices",
        pain_point_category="cashflow", profile_match="fit", product_fit_explanation="fit", evidence="pay late",
        score=80, score_breakdown=ScoreBreakdown(icp_match=20, problem_fit=24, buying_intent=16, urgency=12, recency=8, total=80),
        classification="high_potential",
    )
    storage.save_lead(lead)
    return lead


def reply(lead_id="L1", text="Reminders after day five work better than a monthly email.", account="", comment="", author="", status="draft"):
    return GeneratedReply(
        lead_id=lead_id, value_first=text, platform="reddit", account_id=account, status=status,  # type: ignore[arg-type]
        target_kind="comment" if comment else "post", target_comment_id=comment, target_author=author,
    )


def link_two(storage: DiscoveryStorage):
    svc = AccountService(storage)
    a = svc.link("reddit", "alpha_user")
    b = svc.link("reddit", "beta_user", alias="alt1", focus=["r/freelance"])
    return svc, a, b


# ── Storage ──

def test_two_replies_on_one_lead_keep_separate_targets(storage):
    make_lead(storage)
    storage.save_reply(reply(account="reddit:alpha_user"))
    storage.save_reply(reply(text="Second answer about retainers.", comment="c1", author="bob", account="reddit:alpha_user"), keep_others=True)
    assert {r.target_key for r in storage.list_replies_for_lead("L1")} == {"post", "comment:c1"}


def test_new_draft_for_same_target_replaces_the_old_one(storage):
    make_lead(storage)
    first = reply()
    storage.save_reply(first)
    second = reply(text="A rewritten answer with other words entirely.")
    storage.save_reply(second)
    rows = storage.list_replies_for_lead("L1")
    assert len(rows) == 1 and rows[0].value_first.startswith("A rewritten")


def test_old_database_with_one_reply_per_lead_migrates(tmp_path: Path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE replies (id TEXT PRIMARY KEY, lead_id TEXT UNIQUE, status TEXT, selected_version TEXT, data TEXT, created_at REAL, updated_at REAL)")
    old = reply(lead_id="LX", comment="c9", author="zed")
    conn.execute(
        "INSERT INTO replies VALUES (?,?,?,?,?,?,?)",
        (old.id, "LX", old.status, old.selected_version, old.model_dump_json(), time.time(), time.time()),
    )
    conn.commit()
    conn.close()
    st = DiscoveryStorage(path)
    got = st.get_reply_by_lead_id("LX")
    assert got is not None and got.id == old.id
    st.save_reply(reply(lead_id="LX", text="Another one entirely, new words."), keep_others=True)
    assert len(st.list_replies_for_lead("LX")) == 2
    st.close()


# ── Thread rules ──

def test_one_account_per_thread():
    settings = PostingSettings()
    first = reply(account="reddit:alpha_user", status="approved")
    other = reply(lead_id="L2", account="reddit:beta_user", comment="c1", author="bob", text="Different words about retainers here.")
    code, _ = thread_rules.check_draft([first], other, settings)
    assert code == "thread_account"


def test_target_takes_one_reply():
    first = reply(account="reddit:a", status="approved")
    again = reply(lead_id="L2", account="reddit:a", text="Totally other wording on the same post.")
    assert thread_rules.check_draft([first], again, PostingSettings())[0] == "target_taken"


def test_second_reply_to_another_comment_passes_third_is_capped():
    s = PostingSettings(max_replies_per_thread=2)
    first = reply(account="reddit:a", status="approved")
    second = reply(account="reddit:a", comment="c1", author="bob", text="Retainers fix this for most people I know.")
    assert thread_rules.check_draft([first], second, s, keep_others=True)[0] == "ok"
    third = reply(account="reddit:a", comment="c2", author="cy", text="Net 15 terms help a lot too, in my case.")
    assert thread_rules.check_draft([first, second], third, s, keep_others=True)[0] == "thread_cap"


def test_same_person_and_same_opening_are_blocked():
    s = PostingSettings()
    first = reply(account="reddit:a", comment="c1", author="Bob", status="approved", text="Reminders after day five work best.")
    same_person = reply(account="reddit:a", comment="c2", author="bob", text="A different reply entirely for Bob.")
    assert thread_rules.check_draft([first], same_person, s, keep_others=True)[0] == "same_author"
    same_head = reply(account="reddit:a", comment="c3", author="cy", text="Reminders after day nine change little.")
    assert thread_rules.check_draft([first], same_head, s, keep_others=True)[0] == "same_opening"


def test_publish_gate_rules_product_mention_and_gap():
    s = PostingSettings(min_thread_gap_minutes=60)
    now = time.time()
    sent = reply(account="reddit:a", status="published", text="Tidewatch sends reminders on day five for you.")
    sent.selected_version = "product_aware"
    sent.product_aware = sent.value_first
    sent.published_at = now - 600
    nxt = reply(account="reddit:a", comment="c1", author="bob", text="Net 15 terms help more than reminders do.", status="approved")
    assert thread_rules.check_publish([sent], nxt, "value_first", reply_text := nxt.value_first, s, "Tidewatch", now)[0] == "thread_gap"
    sent.published_at = now - 4000
    assert thread_rules.check_publish([sent], nxt, "value_first", reply_text, s, "Tidewatch", now)[0] == "ok"
    assert thread_rules.check_publish([sent], nxt, "product_aware", reply_text, s, "Tidewatch", now)[0] == "thread_product"


# ── Picking and credentials ──

def test_link_many_accounts_and_alias_clash(storage):
    svc, a, b = link_two(storage)
    assert len(svc.for_platform("reddit")) == 2
    with pytest.raises(AccountError):
        svc.link("reddit", "gamma_user", alias="ALT1")
    svc.link("twitter", "tw_one")
    svc.link("twitter", "tw_two")
    assert len(svc.for_platform("twitter")) == 2


def test_pick_prefers_focus_then_rotates(storage):
    svc, a, b = link_two(storage)
    chosen, _ = svc.pick("reddit", community="r/freelance")
    assert account_key(chosen) == "reddit:beta_user"
    # beta posted today, so another community goes to the account with fewer posts
    storage.log_post("L1", "r1", "reddit", URL, "t", "manual", "published", kind="value_first", account_id="reddit:beta_user")
    chosen, _ = svc.pick("reddit", community="r/saas")
    assert account_key(chosen) == "reddit:alpha_user"


def test_pick_keeps_the_thread_account(storage):
    svc, a, b = link_two(storage)
    held = reply(account="reddit:alpha_user", status="approved")
    chosen, why = svc.pick("reddit", thread=[held], community="r/freelance")
    assert account_key(chosen) == "reddit:alpha_user" and "keeps the thread" in why


def test_pick_skips_accounts_at_their_daily_cap(storage):
    svc, a, b = link_two(storage)
    for i in range(2):   # an unknown account allows daily_limit posts; the default stage caps at 2
        storage.log_post("L1", f"r{i}", "reddit", URL, "t", "manual", "published", kind="value_first", account_id="reddit:beta_user")
    chosen, _ = svc.pick("reddit", community="r/freelance", settings=PostingSettings(daily_limit=2))
    assert account_key(chosen) == "reddit:alpha_user"


def test_credentials_use_account_variables_and_check_the_username(storage, monkeypatch):
    svc, a, b = link_two(storage)
    for name in ("CLIENT_ID", "CLIENT_SECRET", "USERNAME", "PASSWORD"):
        monkeypatch.delenv(f"REDDIT_{name}", raising=False)
    for name, value in (("CLIENT_ID", "id"), ("CLIENT_SECRET", "sec"), ("USERNAME", "beta_user"), ("PASSWORD", "pw")):
        monkeypatch.setenv(f"REDDIT_ALT1_{name}", value)
    assert svc.credentials(b) is not None and svc.credentials(a) is None
    report = svc.credential_report(b)
    assert report["ready"] and all(v["set"] for v in report["variables"])
    assert "pw" not in str(report)
    monkeypatch.setenv("REDDIT_ALT1_USERNAME", "someone_else")
    assert svc.credentials(b) is None
    assert "must equal" in svc.credential_report(b)["note"]


def test_manual_only_platform_reports_no_variables(storage):
    svc = AccountService(storage)
    acc = svc.link("twitter", "tw_one")
    rep = svc.credential_report(acc)
    assert rep["posting"] == "manual" and rep["variables"] == []


# ── Publisher ──

def test_publisher_needs_an_account_when_several_are_linked(storage, profile):
    link_two(storage)
    lead = make_lead(storage)
    r = reply(status="approved", text=LONG)
    storage.save_reply(r)
    pub = CommunityPublisher(storage, profile=profile)
    code, _ = pub.gate(r, lead, PostingSettings(require_rules_ack=False))
    assert code == "account_needed"


def test_publisher_logs_the_account(storage, profile):
    svc, a, b = link_two(storage)
    lead = make_lead(storage)
    r = reply(status="approved", account="reddit:beta_user", text=LONG)
    storage.save_reply(r)
    pub = CommunityPublisher(storage, profile=profile)
    out = pub.publish_or_copy(r, lead, PostingSettings(require_rules_ack=False, require_account_health=False))
    assert out.get("success") and out["account"] == "reddit:beta_user"
    r2 = storage.get_reply(r.id)
    pub.confirm_manual_post(r2, lead, "https://x/y")
    assert storage.count_posts_today("reddit", "reddit:beta_user") == 1
    assert storage.count_posts_today("reddit", "reddit:alpha_user") == 0


def test_second_account_cannot_join_a_thread(storage, profile):
    link_two(storage)
    make_lead(storage)
    first = reply(status="published", account="reddit:alpha_user")
    first.published_at = time.time() - 7200
    storage.save_reply(first)
    lead2 = make_lead(storage, lead_id="L2")
    second = reply(lead_id="L2", status="approved", account="reddit:beta_user", comment="c1", author="bob",
                   text=LONG2)
    storage.save_reply(second)
    pub = CommunityPublisher(storage, profile=profile)
    code, message = pub.gate(second, lead2, PostingSettings(require_rules_ack=False, require_account_health=False))
    assert code == "thread_account" and "alpha_user" in message


def test_draft_for_lead_refuses_a_taken_target(svc, storage, profile):
    link_two(storage)
    lead = make_lead(storage)
    sent = reply(status="published", account="reddit:alpha_user")
    storage.save_reply(sent)
    with pytest.raises(ReplyGenerationError) as exc:
        svc.draft_for_lead(lead, profile, target_mode="post", account="reddit:alpha_user", read_thread=False)
    assert "target_taken" in str(exc.value)


# ── One account names the product per community ──

PA = ("I work on Tidewatch, so weigh this with that in mind. It sends reminders on day five, "
      "so you stop chasing clients by hand, and that is what fixed the same problem for me.")


def test_only_one_account_names_the_product_in_a_community(storage, profile):
    svc, _, _ = link_two(storage)
    accounts = svc.list()
    for a in accounts:
        a.snapshot = {"supported": True, "age_days": 500, "comment_karma": 900, "link_karma": 50, "recent_comments": 20}
    svc._save(accounts)
    make_lead(storage)
    lead2 = make_lead(storage, url=URL.replace("abc123", "zzz999"), lead_id="L2")
    storage.log_post("L1", "r0", "reddit", URL, PA, "manual", "published", kind="product_aware", account_id="reddit:beta_user")
    assert storage.product_posters("reddit", "r/freelance", 7) == ["reddit:beta_user"]
    r = reply(lead_id="L2", status="approved", account="reddit:alpha_user", text=LONG)
    r.product_aware, r.selected_version = PA, "product_aware"
    storage.save_reply(r)
    settings = PostingSettings(require_rules_ack=False, require_account_health=False, max_mention_ratio=1.0)
    pub = CommunityPublisher(storage, profile=profile)
    code, message = pub.gate(r, lead2, settings)
    assert code == "community_overlap" and "beta_user" in message
    # the same account is not blocked by this rule, and the owner can turn the rule off
    settings.product_community_gap_days = 0
    assert pub.gate(r, lead2, settings)[0] != "community_overlap"


def test_the_new_settings_are_bounded():
    s = PostingSettings(max_replies_per_thread=3, min_thread_gap_minutes=0, product_community_gap_days=7)
    assert s.max_replies_per_thread == 3
    with pytest.raises(ValueError):
        PostingSettings(max_replies_per_thread=4)
