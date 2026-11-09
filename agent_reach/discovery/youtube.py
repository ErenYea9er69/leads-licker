# -*- coding: utf-8 -*-
"""YouTube source: find videos, read comments, read transcripts.

Three parts, each optional and each reported on its own:

  Search and comments   YouTube Data API v3. Needs YOUTUBE_API_KEY. A search costs 100 quota units, a video
                        lookup or a comment page costs 1. The default daily quota is 10,000 units, so the
                        app counts what it spends and stops at YOUTUBE_DAILY_QUOTA (default 9000).
  Transcripts           The youtube-transcript-api package (pip install "agent-reach[youtube]"). No key.
                        The app reads the transcript in the owner's language and asks YouTube to translate
                        it when the video has another language.
  Posting               The app never posts to YouTube. The owner pastes the reply under the video or the
                        comment. The Data API needs OAuth consent for writes, which this app does not hold.

Request and response shapes follow the public API reference. The code was not run against YouTube while it
was written, so the unit tests use recorded response shapes. Run `agent-reach discovery check youtube` to test
your key and a transcript fetch from your own machine.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple, Type

import requests

from agent_reach.discovery.thread_check import (
    PLATFORM_MAX_AGE_DAYS,
    ThreadHealth,
    age_in_days,
    youtube_video_id,
)

log = logging.getLogger("agent_reach.discovery")

API = "https://www.googleapis.com/youtube/v3"
QUOTA_KEY = "youtube_quota"
COSTS = {"search": 100, "videos": 1, "commentThreads": 1, "channels": 1}
TRANSCRIPT_CHUNK_SECONDS = 30
_ISO_DURATION = re.compile(r"^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?$")
_WORD = re.compile(r"[a-z]{4,}")


class YouTubeError(RuntimeError):
    """A YouTube call failed. `code` is a short machine word: no_key, quota, comments_disabled, key_rejected, http, network."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def api_key() -> str:
    """The key comes from the environment or the owner-only config file. It never goes in the database."""
    key = os.getenv("YOUTUBE_API_KEY") or os.getenv("GOOGLE_API_KEY_YOUTUBE") or ""
    if key:
        return key
    try:
        from agent_reach.config import Config

        return str(Config(read_only=True).get("youtube_api_key") or "")
    except Exception:
        return ""


def watch_url(video: str) -> str:
    return f"https://www.youtube.com/watch?v={video}"


def comment_link(video: str, comment_id: str) -> str:
    """A link that opens the video with one comment highlighted. The owner replies there."""
    return f"{watch_url(video)}&lc={comment_id}" if comment_id else watch_url(video)


def parse_duration(text: str) -> Optional[int]:
    m = _ISO_DURATION.match(text or "")
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def _quota_day(now: Optional[datetime.datetime] = None) -> str:
    """Google resets the quota at midnight Pacific time. UTC minus eight hours is close enough to stay safe."""
    moment = now or datetime.datetime.now(datetime.timezone.utc)
    return (moment - datetime.timedelta(hours=8)).strftime("%Y-%m-%d")


class Quota:
    """Counts the units this app spent today. The count lives in the settings table. It holds no secret."""

    def __init__(self, storage: Any = None, limit: Optional[int] = None):
        self.storage = storage
        try:
            self.limit = int(limit if limit is not None else os.getenv("YOUTUBE_DAILY_QUOTA", "9000"))
        except ValueError:
            self.limit = 9000

    def used(self) -> int:
        if self.storage is None:
            return 0
        raw = self.storage.get_setting(QUOTA_KEY, {}) or {}
        return int(raw.get("units", 0)) if raw.get("day") == _quota_day() else 0

    def remaining(self) -> int:
        return max(0, self.limit - self.used())

    def spend(self, units: int) -> bool:
        """Reserve units. Returns False when the day's budget cannot cover them."""
        if self.used() + units > self.limit:
            return False
        if self.storage is not None:
            self.storage.set_setting(QUOTA_KEY, {"day": _quota_day(), "units": self.used() + units})
        return True


class YouTubeAPI:
    """The four Data API calls the app needs."""

    def __init__(self, session: Optional[requests.Session] = None, storage: Any = None, key: Optional[str] = None):
        self.session = session or requests.Session()
        self.key = key if key is not None else api_key()
        self.quota = Quota(storage)

    def available(self) -> bool:
        return bool(self.key)

    def _get(self, resource: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.key:
            raise YouTubeError("no_key", "Set YOUTUBE_API_KEY to search YouTube and read its comments.")
        if not self.quota.spend(COSTS[resource]):
            raise YouTubeError(
                "quota",
                f"The app already spent {self.quota.used()} of {self.quota.limit} YouTube quota units today. "
                "It resumes after midnight Pacific time. Raise YOUTUBE_DAILY_QUOTA if your project has a larger quota.",
            )
        try:
            resp = self.session.get(f"{API}/{resource}", params={**params, "key": self.key}, timeout=12)
        except requests.RequestException as exc:
            raise YouTubeError("network", f"YouTube request failed: {type(exc).__name__}") from exc
        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError as exc:
                raise YouTubeError("http", "YouTube returned a body that is not JSON.") from exc
        reason = ""
        try:
            errors = (resp.json().get("error") or {}).get("errors") or []
            reason = str((errors[0] if errors else {}).get("reason") or "")
        except (ValueError, AttributeError, IndexError):
            pass
        if reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise YouTubeError("quota", "YouTube says the project's quota is used up.")
        if reason in ("commentsDisabled", "forbidden") and resource == "commentThreads":
            raise YouTubeError("comments_disabled", "Comments are turned off on this video.")
        if reason in ("keyInvalid", "keyExpired", "accessNotConfigured", "ipRefererBlocked") or resp.status_code in (400, 401):
            raise YouTubeError("key_rejected", f"YouTube rejected the key ({reason or resp.status_code}). Check YOUTUBE_API_KEY and that YouTube Data API v3 is enabled.")
        raise YouTubeError("http", f"YouTube returned http {resp.status_code} {reason}".strip())

    def search(self, query: str, limit: int = 10, days: Optional[int] = None, language: str = "") -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {
            "part": "snippet", "type": "video", "q": query, "maxResults": max(1, min(limit, 25)), "order": "relevance",
        }
        if days:
            since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
            params["publishedAfter"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        if language:
            params["relevanceLanguage"] = language.split("-")[0].lower()
        return list(self._get("search", params).get("items") or [])

    def videos(self, ids: List[str]) -> Dict[str, Dict[str, Any]]:
        if not ids:
            return {}
        data = self._get("videos", {"part": "snippet,statistics,contentDetails,status", "id": ",".join(ids[:50]), "maxResults": 50})
        return {str(v.get("id")): v for v in data.get("items") or [] if v.get("id")}

    def comment_threads(self, video: str, limit: int = 50) -> Dict[str, Any]:
        return self._get("commentThreads", {
            "part": "snippet,replies", "videoId": video, "order": "relevance",
            "maxResults": max(1, min(limit, 100)), "textFormat": "plainText",
        })

    def channel(self, handle: str) -> Optional[Dict[str, Any]]:
        data = self._get("channels", {"part": "snippet,statistics", "forHandle": "@" + handle.lstrip("@")})
        items = data.get("items") or []
        return items[0] if items else None


# ── Pure helpers ──

def video_language(video: Dict[str, Any]) -> str:
    snip = video.get("snippet") or {}
    return str(snip.get("defaultAudioLanguage") or snip.get("defaultLanguage") or "").lower()


def same_language(a: str, b: str) -> bool:
    """True when either side is unknown or the primary language subtags match (en and en-US)."""
    if not a or not b:
        return True
    return a.lower().split("-")[0] == b.lower().split("-")[0]


def judge_youtube(video: Optional[Dict[str, Any]], published_at: Optional[str] = None, now: Optional[datetime.date] = None) -> ThreadHealth:
    """Reply opportunity of one video, from a videos.list item. A missing item gives an unverified record."""
    if not video:
        health = ThreadHealth(verified=False, kind="video", age_days=age_in_days(published_at, now), crowd_limit=2000)
        health.warnings.append("unverified_comment_state")
        return health
    snip, stats, status = video.get("snippet") or {}, video.get("statistics") or {}, video.get("status") or {}
    comments = stats.get("commentCount")
    health = ThreadHealth(
        verified=True,
        commentable=comments is not None,
        num_comments=int(comments) if comments is not None else None,
        score=int(stats["likeCount"]) if stats.get("likeCount") is not None else None,
        age_days=age_in_days(str(snip.get("publishedAt") or published_at or ""), now),
        kind="video",
        crowd_limit=2000,
    )
    duration = parse_duration((video.get("contentDetails") or {}).get("duration", ""))
    if snip.get("liveBroadcastContent") in ("live", "upcoming"):
        health.reject = "live_or_upcoming"
    elif status.get("privacyStatus") not in (None, "public"):
        health.reject = "not_public"
    elif status.get("madeForKids"):
        health.reject = "made_for_kids"   # comments are off and children's content is not a lead
    elif comments is None:
        health.reject = "comments_disabled"   # the API leaves commentCount out when comments are off
    elif duration is not None and duration < 60 and not snip.get("description"):
        health.reject = "too_short"
    if health.reject:
        return health
    if health.age_days is not None and health.age_days > PLATFORM_MAX_AGE_DAYS["youtube"]:
        health.reject = "too_old"
    elif health.num_comments == 0 and health.age_days is not None and health.age_days > 7:
        health.reject = "dead_thread"
    return health


def flatten_comments(data: Dict[str, Any], channel_id: str = "") -> List[Dict[str, Any]]:
    """Turn a commentThreads.list response into the flat comment dicts that thread_comments ranks."""
    out: List[Dict[str, Any]] = []

    def one(item: Dict[str, Any], depth: int, replies: int) -> Dict[str, Any]:
        snip = item.get("snippet") or {}
        created = None
        try:
            created = datetime.datetime.fromisoformat(str(snip.get("publishedAt", "")).replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
        author_channel = ((snip.get("authorChannelId") or {}).get("value")) or ""
        return {
            "id": str(item.get("id") or ""),
            "author": snip.get("authorDisplayName") or "",
            "body": snip.get("textDisplay") or snip.get("textOriginal") or "",
            "score": int(snip.get("likeCount") or 0),
            "depth": depth,
            "created_utc": created,
            "is_submitter": bool(channel_id) and author_channel == channel_id,
            "distinguished": None,
            "stickied": False,
            "reply_count": replies,
        }

    for thread in data.get("items") or []:
        top = (thread.get("snippet") or {}).get("topLevelComment") or {}
        total = int((thread.get("snippet") or {}).get("totalReplyCount") or 0)
        out.append(one(top, 0, total))
        for reply in (thread.get("replies") or {}).get("comments") or []:
            out.append(one(reply, 1, 0))
    return out


def post_info(video: Dict[str, Any], context: str = "") -> Dict[str, Any]:
    snip, stats = video.get("snippet") or {}, video.get("statistics") or {}
    return {
        "id": video.get("id"), "author": snip.get("channelTitle") or "", "channel_id": snip.get("channelId") or "",
        "title": snip.get("title") or "", "selftext": (snip.get("description") or "")[:600],
        "num_comments": int(stats.get("commentCount") or 0), "locked": False, "archived": False,
        "context": context,
    }


# ── Transcripts ──

class _TimeoutSession(requests.Session):
    """The transcript package sets no timeout. A stalled request must not hold a campaign."""

    def request(self, *args: Any, **kwargs: Any):  # type: ignore[override]
        kwargs.setdefault("timeout", 12)
        return super().request(*args, **kwargs)


def _exc(module: Any, *names: str) -> Tuple[Type[BaseException], ...]:
    """The exception classes this version of the transcript package defines. Older versions lack some."""
    found = tuple(getattr(module, n) for n in names if isinstance(getattr(module, n, None), type) and issubclass(getattr(module, n), BaseException))
    return found or (_Never,)


class _Never(Exception):
    """Stands in when a package version defines none of the wanted exceptions."""


def _chunks(snippets: List[Any]) -> List[Dict[str, Any]]:
    """Join caption lines into windows of about 30 seconds, each tagged with its start."""
    chunks: List[Dict[str, Any]] = []
    for sn in snippets:
        start = float(getattr(sn, "start", 0.0))
        text = re.sub(r"\s+", " ", str(getattr(sn, "text", "")).replace("\n", " ")).strip()
        if not text or (text.startswith("[") and text.endswith("]")):   # [Music], [Applause]
            continue
        if chunks and start - chunks[-1]["start"] < TRANSCRIPT_CHUNK_SECONDS:
            chunks[-1]["text"] += " " + text
        else:
            chunks.append({"start": int(start), "text": text})
    return chunks


def fetch_transcript(video: str, languages: Optional[List[str]] = None, translate_to: str = "") -> Dict[str, Any]:
    """Read one transcript. Returns {"ok": True, ...} or {"ok": False, "error": code, "message": text}.

    `languages` lists preferred languages in order. When the video has none of them, the first available
    transcript is used, and `translate_to` asks YouTube to translate it when the video allows that.
    Error codes: not_installed, disabled, no_transcript, blocked, unavailable, failed.
    """
    try:
        import youtube_transcript_api as errs
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return {"ok": False, "error": "not_installed", "message": 'Install the transcript reader: pip install "agent-reach[youtube]".'}
    wanted = [x.split("-")[0].lower() for x in (languages or ["en"]) if x] or ["en"]
    target = (translate_to or wanted[0]).split("-")[0].lower()
    try:
        api = YouTubeTranscriptApi(http_client=_TimeoutSession())
        available = list(api.list(video))
        if not available:
            return {"ok": False, "error": "no_transcript", "message": "This video has no transcript."}
        by_lang = {t.language_code.split("-")[0].lower(): t for t in available}
        manual = [t for t in available if not t.is_generated]
        pick = next((by_lang[w] for w in wanted if w in by_lang), None) or (manual[0] if manual else available[0])
        translated = False
        if pick.language_code.split("-")[0].lower() != target and pick.is_translatable:
            try:
                pick, translated = pick.translate(target), True
            except _exc(errs, "NotTranslatable", "TranslationLanguageNotAvailable"):
                pass
        fetched = pick.fetch()
    except _exc(errs, "TranscriptsDisabled"):
        return {"ok": False, "error": "disabled", "message": "The channel turned transcripts off for this video."}
    except _exc(errs, "NoTranscriptFound"):
        return {"ok": False, "error": "no_transcript", "message": "No transcript in a usable language."}
    except _exc(errs, "IpBlocked", "RequestBlocked"):
        return {"ok": False, "error": "blocked", "message": "YouTube blocked the transcript request from this network. Try again later or from another network."}
    except _exc(errs, "VideoUnavailable", "VideoUnplayable", "InvalidVideoId", "AgeRestricted"):
        return {"ok": False, "error": "unavailable", "message": "The video is private, removed, age restricted or not playable."}
    except Exception as exc:   # the package scrapes YouTube, so any change on their side surfaces here
        return {"ok": False, "error": "failed", "message": f"Transcript read failed: {type(exc).__name__}"}
    chunks = _chunks(list(fetched))
    text = " ".join(c["text"] for c in chunks)
    return {
        "ok": True, "video_id": video, "language_code": fetched.language_code, "is_generated": bool(fetched.is_generated),
        "translated": translated, "translated_to": target if translated else "", "chunks": len(chunks),
        "characters": len(text), "segments": chunks,
    }


def _mmss(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def excerpt(segments: List[Dict[str, Any]], keywords: str = "", max_chars: int = 900) -> str:
    """The parts of a transcript that matter for a reply: the windows that share words with the search, in time order."""
    if not segments:
        return ""
    wanted = set(_WORD.findall(keywords.lower()))

    def overlap(i: int) -> int:
        return len(wanted & set(_WORD.findall(segments[i]["text"].lower())))

    scored = sorted(range(len(segments)), key=lambda i: (-overlap(i), i))
    if scored and overlap(scored[0]) > 0:
        scored = [i for i in scored if overlap(i) > 0]   # only windows that share words with the search
    else:
        scored = scored[:2]   # no match: the opening says what the video is about
    chosen: List[int] = []
    used = 0
    for i in scored:
        cost = len(segments[i]["text"]) + 8
        if chosen and used + cost > max_chars:
            continue
        chosen.append(i)
        used += cost
        if used >= max_chars or len(chosen) >= 4:
            break
    lines = [f"[{_mmss(segments[i]['start'])}] {segments[i]['text']}" for i in sorted(chosen)]
    return "\n".join(lines)[: max_chars + 40]


def transcript_note(info: Dict[str, Any]) -> str:
    """One line that tells the reader how the transcript came about."""
    if not info.get("ok"):
        return ""
    kind = "auto-generated" if info.get("is_generated") else "uploaded by the channel"
    base = f"Transcript ({info.get('language_code')}, {kind}"
    return base + (f", translated to {info['translated_to']})" if info.get("translated") else ")")


def check(session: Optional[requests.Session] = None, video: str = "dQw4w9WgXcQ", storage: Any = None) -> Dict[str, Any]:
    """Owner-run test of the key and the transcript reader. Costs 2 quota units."""
    api = YouTubeAPI(session, storage)
    report: Dict[str, Any] = {"key_set": api.available(), "quota_used_today": api.quota.used(), "quota_limit": api.quota.limit}
    if api.available():
        try:
            found = api.videos([video])
            report["api"] = "ok" if found else "key works, video not found"
            try:
                api.comment_threads(video, 1)
                report["comments"] = "ok"
            except YouTubeError as exc:
                report["comments"] = f"{exc.code}: {exc}"
        except YouTubeError as exc:
            report["api"] = f"{exc.code}: {exc}"
    else:
        report["api"] = "no key. Set YOUTUBE_API_KEY."
    tr = fetch_transcript(video, ["en"])
    report["transcripts"] = "ok" if tr.get("ok") else f"{tr.get('error')}: {tr.get('message')}"
    return report


def split_video_ref(url: str) -> Tuple[str, str]:
    """(video id, comment id) from a watch link that may carry &lc=."""
    m = re.search(r"[?&]lc=([A-Za-z0-9_.-]+)", url or "")
    return youtube_video_id(url) or "", (m.group(1) if m else "")
