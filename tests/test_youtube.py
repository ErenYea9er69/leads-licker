"""YouTube source. Responses follow the Data API reference shapes. Nothing here reaches the network."""

from __future__ import annotations

import sys
from typing import Any, Dict, List

import pytest

from agent_reach.discovery import thread_comments, youtube
from agent_reach.discovery.accounts import AccountService
from agent_reach.discovery.harvester import CommunityHarvester
from agent_reach.discovery.models import ReplyTarget
from agent_reach.discovery.thread_check import canonical_url, youtube_video_id

VID = "dQw4w9WgXcQ"


class Resp:
    def __init__(self, status: int, body: Any):
        self.status_code, self._body = status, body

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class FakeSession:
    """Answers by resource name. `routes` maps "search", "videos", "commentThreads" or "channels" to a Resp."""

    def __init__(self, routes: Dict[str, Resp]):
        self.routes, self.calls = routes, []

    def get(self, url: str, params: Any = None, **kw: Any) -> Resp:
        name = url.rsplit("/", 1)[-1]
        self.calls.append((name, dict(params or {})))
        return self.routes[name]


def video(vid: str = VID, comments: Any = "12", **over: Any) -> Dict[str, Any]:
    stats = {"viewCount": "1000", "likeCount": "50"}
    if comments is not None:
        stats["commentCount"] = comments
    base = {
        "id": vid,
        "snippet": {
            "publishedAt": "2026-10-20T10:00:00Z", "channelId": "UCowner", "channelTitle": "Freelance Finance",
            "title": "How to stop clients paying late", "description": "Reminders and payment terms for freelancers.",
            "defaultAudioLanguage": "en", "liveBroadcastContent": "none",
        },
        "contentDetails": {"duration": "PT12M5S"},
        "status": {"privacyStatus": "public", "madeForKids": False},
        "statistics": stats,
    }
    base.update(over)
    return base


THREADS = {"items": [
    {"id": "t1", "snippet": {"totalReplyCount": 1, "topLevelComment": {"id": "UgzTop", "snippet": {
        "authorDisplayName": "Bob", "authorChannelId": {"value": "UCbob"}, "textDisplay": "Is there a tool that sends the reminders for me?",
        "likeCount": 4, "publishedAt": "2026-10-30T10:00:00Z"}}},
     "replies": {"comments": [{"id": "UgzTop.r1", "snippet": {
         "authorDisplayName": "Cy", "authorChannelId": {"value": "UCcy"}, "textDisplay": "I use a spreadsheet.", "likeCount": 0,
         "publishedAt": "2026-10-31T10:00:00Z"}}]}},
    {"id": "t2", "snippet": {"totalReplyCount": 0, "topLevelComment": {"id": "UgzOwner", "snippet": {
        "authorDisplayName": "Freelance Finance", "authorChannelId": {"value": "UCowner"}, "textDisplay": "Thanks for watching all of this.",
        "likeCount": 1, "publishedAt": "2026-10-21T10:00:00Z"}}}},
]}


# ── Pure helpers ──

def test_every_link_form_gives_one_canonical_url():
    for u in (f"https://www.youtube.com/watch?v={VID}&t=30s", f"https://youtu.be/{VID}?si=x", f"https://m.youtube.com/shorts/{VID}",
              f"https://www.youtube.com/watch?list=PL1&v={VID}&lc=Ugx"):
        assert canonical_url(u) == f"https://youtube.com/watch?v={VID}"
    assert youtube_video_id("https://example.com/watch?v=dQw4w9WgXcQ") is None


def test_parse_duration():
    assert youtube.parse_duration("PT12M5S") == 725 and youtube.parse_duration("PT45S") == 45
    assert youtube.parse_duration("P0D") == 0 and youtube.parse_duration("junk") is None and youtube.parse_duration("PT") is None


@pytest.mark.parametrize("meta,code", [
    (video(), None),
    (video(comments=None), "comments_disabled"),
    (video(comments="0"), "dead_thread"),
    (video(snippet={**video()["snippet"], "liveBroadcastContent": "live"}), "live_or_upcoming"),
    (video(status={"privacyStatus": "public", "madeForKids": True}), "made_for_kids"),
    (video(status={"privacyStatus": "unlisted", "madeForKids": False}), "not_public"),
    (video(snippet={**video()["snippet"], "publishedAt": "2025-01-01T00:00:00Z"}), "too_old"),
])
def test_video_health(meta, code):
    import datetime

    health = youtube.judge_youtube(meta, now=datetime.date(2026, 11, 7))
    assert health.reject == code
    if code is None:
        assert health.verified and health.commentable and health.num_comments == 12 and not health.crowded


def test_video_without_api_data_is_unverified():
    h = youtube.judge_youtube(None, "2026-10-20")
    assert not h.verified and "unverified_comment_state" in h.warnings and h.reject is None


def test_comment_threads_flatten_with_replies_and_owner_flag():
    flat = youtube.flatten_comments(THREADS, "UCowner")
    assert [c["id"] for c in flat] == ["UgzTop", "UgzTop.r1", "UgzOwner"]
    assert flat[0]["reply_count"] == 1 and flat[1]["depth"] == 1 and flat[2]["is_submitter"] and not flat[0]["is_submitter"]
    assert flat[0]["created_utc"] and flat[0]["score"] == 4


def test_language_match_ignores_region_and_unknown():
    assert youtube.same_language("en-US", "en") and youtube.same_language("", "fr") and not youtube.same_language("es", "en")


# ── Quota and API errors ──

def test_quota_counts_and_blocks(storage):
    q = youtube.Quota(storage, limit=250)
    assert q.spend(100) and q.spend(100) and not q.spend(100) and q.used() == 200 and q.remaining() == 50


def test_api_without_key_says_what_to_set(storage, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    monkeypatch.setattr(youtube, "api_key", lambda: "")
    api = youtube.YouTubeAPI(FakeSession({}), storage)
    with pytest.raises(youtube.YouTubeError) as exc:
        api.search("x")
    assert exc.value.code == "no_key" and "YOUTUBE_API_KEY" in str(exc.value)


@pytest.mark.parametrize("status,reason,code,resource", [
    (403, "quotaExceeded", "quota", "search"),
    (400, "keyInvalid", "key_rejected", "videos"),
    (403, "commentsDisabled", "comments_disabled", "commentThreads"),
    (500, "backendError", "http", "videos"),
])
def test_api_error_codes(storage, status, reason, code, resource):
    body = {"error": {"code": status, "errors": [{"reason": reason}]}}
    api = youtube.YouTubeAPI(FakeSession({resource: Resp(status, body)}), storage, key="k")
    call = {"search": lambda: api.search("q"), "videos": lambda: api.videos([VID]), "commentThreads": lambda: api.comment_threads(VID)}[resource]
    with pytest.raises(youtube.YouTubeError) as exc:
        call()
    assert exc.value.code == code


def test_api_stops_before_the_daily_budget_is_gone(storage, monkeypatch):
    monkeypatch.setenv("YOUTUBE_DAILY_QUOTA", "150")
    session = FakeSession({"search": Resp(200, {"items": []})})
    api = youtube.YouTubeAPI(session, storage, key="k")
    api.search("one")
    with pytest.raises(youtube.YouTubeError) as exc:
        api.search("two")
    assert exc.value.code == "quota" and len(session.calls) == 1   # the second call never left the machine


# ── Transcripts ──

class FakeTranscript:
    def __init__(self, code: str, generated: bool, translatable: bool = True, lines: List[str] | None = None):
        self.language_code, self.is_generated, self.is_translatable = code, generated, translatable
        self.lines, self.translated_to = lines or ["clients pay late", "send reminders on day five"], ""

    def translate(self, code: str) -> "FakeTranscript":
        t = FakeTranscript(code, True, False, self.lines)
        t.translated_to = code
        return t

    def fetch(self) -> Any:
        snippets = [type("S", (), {"text": text, "start": i * 40.0, "duration": 4.0})() for i, text in enumerate(self.lines)]
        return type("F", (), {"snippets": snippets, "language_code": self.language_code, "is_generated": self.is_generated,
                              "__iter__": lambda self: iter(self.snippets), "__len__": lambda self: len(self.snippets)})()


def fake_api(transcripts: List[FakeTranscript] | None = None, raises: Exception | None = None):
    class Api:
        def __init__(self, *a: Any, **k: Any):
            pass

        def list(self, video_id: str):
            if raises:
                raise raises
            return list(transcripts or [])

    return Api


def test_transcript_in_the_owner_language_is_used_as_is(monkeypatch):
    mod = pytest.importorskip("youtube_transcript_api")

    monkeypatch.setattr(mod, "YouTubeTranscriptApi", fake_api([FakeTranscript("es", False), FakeTranscript("en", True)]))
    out = youtube.fetch_transcript(VID, ["en"], "en")
    assert out["ok"] and out["language_code"] == "en" and not out["translated"] and out["chunks"] == 2


def test_transcript_in_another_language_is_translated(monkeypatch):
    mod = pytest.importorskip("youtube_transcript_api")

    monkeypatch.setattr(mod, "YouTubeTranscriptApi", fake_api([FakeTranscript("es", False)]))
    out = youtube.fetch_transcript(VID, ["en"], "en")
    assert out["ok"] and out["translated"] and out["translated_to"] == "en"
    assert youtube.transcript_note(out) == "Transcript (en, auto-generated, translated to en)"


def test_untranslatable_transcript_keeps_its_language(monkeypatch):
    mod = pytest.importorskip("youtube_transcript_api")

    monkeypatch.setattr(mod, "YouTubeTranscriptApi", fake_api([FakeTranscript("de", False, translatable=False)]))
    out = youtube.fetch_transcript(VID, ["en"], "en")
    assert out["ok"] and out["language_code"] == "de" and not out["translated"]


@pytest.mark.parametrize("name,code", [
    ("TranscriptsDisabled", "disabled"), ("NoTranscriptFound", "no_transcript"), ("VideoUnavailable", "unavailable"),
])
def test_transcript_errors_have_codes(monkeypatch, name, code):
    mod = pytest.importorskip("youtube_transcript_api")

    exc = getattr(mod, name)
    try:
        error = exc(VID)
    except TypeError:
        error = exc(VID, ["en"], None)
    monkeypatch.setattr(mod, "YouTubeTranscriptApi", fake_api(raises=error))
    out = youtube.fetch_transcript(VID, ["en"])
    assert not out["ok"] and out["error"] == code


def test_blocked_network_and_unexpected_errors(monkeypatch):
    mod = pytest.importorskip("youtube_transcript_api")

    monkeypatch.setattr(mod, "YouTubeTranscriptApi", fake_api(raises=mod.IpBlocked(VID)))
    assert youtube.fetch_transcript(VID)["error"] == "blocked"
    monkeypatch.setattr(mod, "YouTubeTranscriptApi", fake_api(raises=ValueError("parse")))
    assert youtube.fetch_transcript(VID)["error"] == "failed"


def test_missing_package_gives_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "youtube_transcript_api", None)
    out = youtube.fetch_transcript(VID)
    assert out["error"] == "not_installed" and "agent-reach[youtube]" in out["message"]


def test_excerpt_prefers_windows_that_match_the_search_and_keeps_time_order():
    segs = [{"start": 0, "text": "welcome to the channel"}, {"start": 40, "text": "late invoices hurt cash flow"},
            {"start": 80, "text": "sponsor message"}, {"start": 120, "text": "send reminders for late invoices"}]
    out = youtube.excerpt(segs, "late invoices reminders", max_chars=120)
    assert out.splitlines()[0].startswith("[00:40]") and "[02:00]" in out and "sponsor" not in out


# ── Harvest ──

def search_hit(vid: str = VID) -> Dict[str, Any]:
    return {"id": {"videoId": vid}, "snippet": {"publishedAt": "2026-10-20T10:00:00Z", "channelTitle": "Freelance Finance", "title": "How to stop clients paying late"}}


def harvester(storage, routes, monkeypatch, transcript=None):
    monkeypatch.setattr(youtube, "api_key", lambda: "k")
    monkeypatch.setattr(youtube, "fetch_transcript", lambda *a, **k: transcript or {"ok": False, "error": "disabled", "message": "off"})
    return CommunityHarvester(storage, session=FakeSession(routes))


def test_harvest_builds_an_item_from_video_transcript_and_comments(storage, monkeypatch):
    tr = {"ok": True, "language_code": "en", "is_generated": True, "translated": False, "translated_to": "", "characters": 40,
          "segments": [{"start": 70, "text": "send reminders on day five"}]}
    h = harvester(storage, {"search": Resp(200, {"items": [search_hit()]}), "videos": Resp(200, {"items": [video()]}),
                            "commentThreads": Resp(200, THREADS)}, monkeypatch, tr)
    items = h.search_youtube("clients paying late", limit=3)
    assert len(items) == 1
    it = items[0]
    assert it.platform == "youtube" and it.url == f"https://youtube.com/watch?v={VID}" and it.community == "Freelance Finance"
    assert "Transcript (en, auto-generated)" in it.content and "[01:10] send reminders on day five" in it.content
    assert "Top comments:" in it.content and "Bob: Is there a tool" in it.content and "I use a spreadsheet" not in it.content
    assert it.thread_health["verified"] and it.thread_health["num_comments"] == 12
    assert h.diagnostics["youtube_transcript_ok"] == 1


def test_harvest_drops_videos_that_cannot_take_a_comment(storage, monkeypatch):
    routes = {"search": Resp(200, {"items": [search_hit()]}), "videos": Resp(200, {"items": [video(comments=None)]})}
    h = harvester(storage, routes, monkeypatch)
    assert h.search_youtube("clients paying late") == []
    assert h.diagnostics["rejected:comments_disabled"] == 1


def test_harvest_drops_other_language_videos(storage, monkeypatch):
    meta = video(snippet={**video()["snippet"], "defaultAudioLanguage": "fr"})
    h = harvester(storage, {"search": Resp(200, {"items": [search_hit()]}), "videos": Resp(200, {"items": [meta]})}, monkeypatch)
    assert h.search_youtube("clients paying late") == []
    assert h.diagnostics["rejected:language_mismatch"] == 1


def test_harvest_survives_a_missing_transcript(storage, monkeypatch):
    routes = {"search": Resp(200, {"items": [search_hit()]}), "videos": Resp(200, {"items": [video()]}), "commentThreads": Resp(200, THREADS)}
    h = harvester(storage, routes, monkeypatch)
    items = h.search_youtube("clients paying late")
    assert len(items) == 1 and "Transcript" not in items[0].content
    assert h.diagnostics["youtube_transcript:disabled"] == 1


def test_harvest_falls_back_to_web_search_when_the_api_fails(storage, monkeypatch):
    body = {"error": {"code": 403, "errors": [{"reason": "quotaExceeded"}]}}
    h = harvester(storage, {"search": Resp(403, body)}, monkeypatch)
    monkeypatch.setattr(h, "_search", lambda q, n, days=None: [
        {"url": f"https://www.youtube.com/watch?v={VID}&feature=share", "title": "Stop late payments - YouTube", "text": "freelance invoices", "published_at": "2026-10-20", "author": None}])
    items = h.search_youtube("clients paying late")
    assert h.diagnostics["youtube_api:quota"] == 1
    assert len(items) == 1 and items[0].thread_health["verified"] is False and "Top comments" not in items[0].content


def test_harvest_without_a_key_uses_web_search(storage, monkeypatch):
    monkeypatch.setattr(youtube, "api_key", lambda: "")
    monkeypatch.setattr(youtube, "fetch_transcript", lambda *a, **k: {"ok": False, "error": "disabled", "message": ""})
    h = CommunityHarvester(storage, session=FakeSession({}))
    monkeypatch.setattr(h, "_search", lambda q, n, days=None: [
        {"url": f"https://youtu.be/{VID}", "title": "Late payments - YouTube", "text": "", "published_at": "2026-10-20", "author": None}])
    assert len(h.search_youtube("clients paying late")) == 1


# ── Comments as reply targets ──

def test_video_comments_rank_as_targets_with_transcript_context(storage, monkeypatch):
    monkeypatch.setattr(youtube, "api_key", lambda: "k")
    monkeypatch.setattr(youtube, "fetch_transcript", lambda *a, **k: {
        "ok": True, "language_code": "en", "is_generated": False, "translated": False, "translated_to": "",
        "segments": [{"start": 70, "text": "send reminders on day five"}]})
    session = FakeSession({"videos": Resp(200, {"items": [video()]}), "commentThreads": Resp(200, THREADS)})
    post, comments, warnings = thread_comments.fetch_comments(f"https://youtu.be/{VID}", session, storage=storage)
    assert not warnings and post["author"] == "Freelance Finance" and "[01:10]" in post["context"]
    targets = thread_comments.rank_targets(post, comments)
    comment_targets = [t for t in targets if t.target_kind == "comment"]
    assert comment_targets[0].target_comment_id == "UgzTop" and comment_targets[0].target_author == "Bob"
    assert all(t.target_author != "Freelance Finance" for t in comment_targets)   # not the channel's own comment
    assert "[01:10]" in targets[0].context


def test_video_comments_without_a_key_say_so(monkeypatch):
    monkeypatch.setattr(youtube, "api_key", lambda: "")
    post, comments, warnings = thread_comments.fetch_comments(f"https://youtu.be/{VID}", FakeSession({}))
    assert not post and not comments and "YOUTUBE_API_KEY" in warnings[0]


def test_disabled_comments_return_a_warning(monkeypatch):
    monkeypatch.setattr(youtube, "api_key", lambda: "k")
    body = {"error": {"code": 403, "errors": [{"reason": "commentsDisabled"}]}}
    session = FakeSession({"videos": Resp(200, {"items": [video()]}), "commentThreads": Resp(403, body)})
    post, comments, warnings = thread_comments.fetch_comments(f"https://youtu.be/{VID}", session)
    assert not comments and "turned off" in warnings[0]


def test_reply_prompt_carries_the_transcript_context(storage, profile):
    from agent_reach.discovery.models import LeadQualification, ScoreBreakdown
    from agent_reach.discovery.reply_generator import ReplyGenerator

    lead = LeadQualification(
        id="L", discovered_item_id="i", title="t", url=f"https://youtube.com/watch?v={VID}", platform="youtube", community="c",
        author="a", published_at="2026-10-20", excerpt="e", customer_problem="late invoices", pain_point_category="p",
        profile_match="m", product_fit_explanation="f", evidence="e", score=70,
        score_breakdown=ScoreBreakdown(icp_match=10, problem_fit=20, buying_intent=10, urgency=10, recency=10, total=60),
    )
    target = ReplyTarget(target_kind="comment", target_comment_id="UgzTop", target_author="Bob", target_text="Is there a tool?",
                         context="Transcript (en, auto-generated)\n[01:10] send reminders on day five")
    ctx = ReplyGenerator().build_prompts(lead, profile, target=target)
    assert "[01:10] send reminders on day five" in ctx["prompt"] and "Do not describe the video" in ctx["prompt"]
    assert ctx["max_words"] <= 70


# ── Accounts and links ──

def test_youtube_accounts_link_many_and_read_the_channel(storage, monkeypatch):
    monkeypatch.setattr(youtube, "api_key", lambda: "k")
    channel = {"items": [{"snippet": {"publishedAt": "2023-01-01T00:00:00Z"}, "statistics": {"subscriberCount": "120", "videoCount": "30"}}]}
    svc = AccountService(storage, FakeSession({"channels": Resp(200, channel)}))
    a = svc.link("youtube", "@FreelanceFinance")
    svc.link("youtube", "second_channel")
    assert a.handle == "FreelanceFinance" and len(svc.for_platform("youtube")) == 2
    acc = svc.refresh("youtube", "FreelanceFinance")
    assert acc.snapshot["supported"] and acc.snapshot["age_days"] > 900 and acc.snapshot["subscribers"] == "120"
    assert svc.credential_report(acc)["posting"] == "manual"


def test_manual_post_link_opens_the_comment(storage):
    from agent_reach.discovery.models import GeneratedReply
    from agent_reach.discovery.publisher import CommunityPublisher
    from tests.test_multi_account import make_lead

    lead = make_lead(storage, url=f"https://youtube.com/watch?v={VID}")
    lead.platform = "youtube"
    r = GeneratedReply(lead_id=lead.id, value_first="x", target_kind="comment", target_comment_id="UgzTop", platform="youtube")
    assert CommunityPublisher._target_link(r, lead) == f"https://www.youtube.com/watch?v={VID}&lc=UgzTop"
    top = GeneratedReply(lead_id=lead.id, value_first="x", platform="youtube")
    assert CommunityPublisher._target_link(top, lead) == f"https://www.youtube.com/watch?v={VID}"
