# -*- coding: utf-8 -*-
"""Thread verification for lead discovery.

A lead only has value when a person still replies to it. This module answers
three questions before a thread reaches the qualifier:

1. Is the thread open? Reddit archives posts after about six months and locks
   some earlier. HN closes old threads. GitHub issues close or lock.
2. Is it a real discussion? Pricing pages, launch posts and listicles never
   hold a buyer asking for help.
3. Does anyone talk there? A thread with zero replies after two weeks is dead.

Every function here is pure or takes an injected HTTP session, so tests run
offline.
"""

from __future__ import annotations

import datetime
import logging
import os
import re
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests

log = logging.getLogger("agent_reach.discovery")

# Reddit archives a post six months after creation; replies are then blocked.
REDDIT_ARCHIVE_DAYS = 180

# Maximum age in days for a thread to count as a live lead, per platform.
# Reddit stays under the archive limit so a reply still lands after review.
# The HN value is a conservative guess. Raise it if you see good older threads.
PLATFORM_MAX_AGE_DAYS: Dict[str, int] = {
    "reddit": 150,
    "hackernews": 14,
    "github": 365,
    "twitter": 90,
    "quora": 730,
    "web": 365,
    "youtube": 180,
}

# A thread with no replies after this many days counts as dead.
DEAD_THREAD_DAYS: Dict[str, int] = {
    "reddit": 14,
    "hackernews": 3,
    "github": 60,
    "twitter": 14,
    "web": 30,
    "youtube": 14,
}

# A thread this crowded buries a new reply.
CROWDED_COMMENTS = 80

USER_AGENT = "Mozilla/5.0 (compatible; AgentReachLeadAgent/2.1; +https://github.com/)"


# ── URL helpers ─────────────────────────────────────────────────────────────

_TRACKING_PARAM = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|ref_|share$|context$|source$|si$)", re.I)
_REDDIT_ID = re.compile(r"(?:reddit\.com/(?:r/[^/]+/)?comments/|redd\.it/)([a-z0-9]+)", re.I)
_REDDIT_SUB = re.compile(r"reddit\.com/(r/[A-Za-z0-9_]+)", re.I)
_TWEET_ID = re.compile(r"/(?:status|statuses|thread)/(\d+)")


def reddit_post_id(url: str) -> Optional[str]:
    m = _REDDIT_ID.search(url or "")
    return m.group(1).lower() if m else None


_YT_ID = re.compile(r"(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|embed/|live/|v/))([A-Za-z0-9_-]{11})")


def youtube_video_id(url: str) -> Optional[str]:
    m = _YT_ID.search(url or "")
    return m.group(1) if m else None


def canonical_url(url: str) -> str:
    """Collapse mirrors, tracking params and slugs so one thread has one key."""
    raw = (url or "").strip()
    if not raw:
        return raw
    try:
        parts = urllib.parse.urlsplit(raw)
    except ValueError:
        return raw
    host = (parts.hostname or "").lower()
    for prefix in ("www.", "old.", "new.", "np.", "m.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break

    pid = reddit_post_id(raw)
    if pid and (host.endswith("reddit.com") or host == "redd.it"):
        sub = _REDDIT_SUB.search(raw)
        return f"https://reddit.com/{sub.group(1).lower()}/comments/{pid}" if sub else f"https://reddit.com/comments/{pid}"

    yt = youtube_video_id(raw)
    if yt and (host.endswith("youtube.com") or host in ("youtu.be", "youtube-nocookie.com")):
        return f"https://youtube.com/watch?v={yt}"

    if host in ("x.com", "twitter.com"):
        tid = _TWEET_ID.search(parts.path)
        if tid:
            return f"https://x.com/i/status/{tid.group(1)}"

    query = sorted(
        (k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=False)
        if not _TRACKING_PARAM.match(k)
    )
    path = parts.path.rstrip("/") or ""
    return urllib.parse.urlunsplit(("https", host, path, urllib.parse.urlencode(query), ""))


def host_of(url: str) -> str:
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def age_in_days(date_text: Optional[str], now: Optional[datetime.date] = None) -> Optional[int]:
    """Whole days since an ISO date or datetime string. None when unparseable."""
    if not date_text:
        return None
    try:
        day = datetime.date.fromisoformat(str(date_text).strip()[:10])
    except ValueError:
        return None
    return ((now or datetime.date.today()) - day).days


# ── Health record ───────────────────────────────────────────────────────────

@dataclass
class ThreadHealth:
    """What the harvester knows about a thread's reply opportunity."""

    verified: bool = False          # numbers came from the platform, not a guess
    commentable: Optional[bool] = None
    num_comments: Optional[int] = None
    score: Optional[int] = None
    age_days: Optional[int] = None
    kind: str = "discussion"
    warnings: List[str] = field(default_factory=list)
    reject: Optional[str] = None    # machine code. None means the thread passes.
    crowd_limit: int = CROWDED_COMMENTS   # a video takes far more comments than a forum thread before a reply is buried

    @property
    def crowded(self) -> bool:
        return (self.num_comments or 0) >= self.crowd_limit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "commentable": self.commentable,
            "num_comments": self.num_comments,
            "score": self.score,
            "age_days": self.age_days,
            "kind": self.kind,
            "warnings": list(self.warnings),
            "crowded": self.crowded,
        }


def _apply_age_and_activity(health: ThreadHealth, platform: str) -> ThreadHealth:
    """Shared age and dead-thread rules. Mutates and returns health."""
    if health.reject:
        return health
    max_age = PLATFORM_MAX_AGE_DAYS.get(platform, 365)
    if health.age_days is not None and health.age_days > max_age:
        health.reject = "too_old"
        return health
    dead_after = DEAD_THREAD_DAYS.get(platform)
    if (
        dead_after is not None
        and health.num_comments == 0
        and health.age_days is not None
        and health.age_days > dead_after
    ):
        health.reject = "dead_thread"
    return health


# ── Reddit ──────────────────────────────────────────────────────────────────

_PROMO_FLAIR = re.compile(r"promot|showcase|launch|self[- ]?promo|advert|i made|i built|show off", re.I)


class RedditMeta:
    """Reads post metadata (comments, archived, locked) from Reddit.

    Uses an app-only OAuth token when client credentials exist. Falls back to
    the public JSON endpoint, which Reddit often blocks. On any failure it
    returns nothing, and the caller falls back to an age estimate.
    """

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        session: Optional[requests.Session] = None,
    ):
        self.client_id = client_id or os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("REDDIT_CLIENT_SECRET")
        if not (self.client_id and self.client_secret):
            try:
                from agent_reach.config import Config

                cfg = Config(read_only=True)
                self.client_id = self.client_id or cfg.get("reddit_client_id")
                self.client_secret = self.client_secret or cfg.get("reddit_client_secret")
            except Exception:
                pass
        self.session = session or requests.Session()
        self._token: Optional[str] = None
        self._token_expiry = 0.0
        self.last_error: Optional[str] = None

    def _bearer(self) -> Optional[str]:
        if not (self.client_id and self.client_secret):
            return None
        if self._token and time.time() < self._token_expiry - 30:
            return self._token
        try:
            resp = self.session.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(self.client_id, self.client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )
            if resp.status_code != 200:
                self.last_error = f"reddit token http {resp.status_code}"
                return None
            body = resp.json()
            self._token = body.get("access_token")
            self._token_expiry = time.time() + float(body.get("expires_in", 3600))
            return self._token
        except (requests.RequestException, ValueError) as exc:
            self.last_error = f"reddit token {type(exc).__name__}"
            return None

    def fetch(self, post_ids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Return {post_id: data}. Missing ids mean Reddit gave no answer."""
        ids = [i for i in dict.fromkeys(post_ids) if i]
        out: Dict[str, Dict[str, Any]] = {}
        token = self._bearer()
        for start in range(0, len(ids), 50):
            chunk = ids[start:start + 50]
            names = ",".join(f"t3_{i}" for i in chunk)
            if token:
                url = f"https://oauth.reddit.com/by_id/{names}?raw_json=1"
                headers = {"User-Agent": USER_AGENT, "Authorization": f"Bearer {token}"}
            else:
                url = f"https://www.reddit.com/by_id/{names}.json?raw_json=1"
                headers = {"User-Agent": USER_AGENT}
            try:
                resp = self.session.get(url, headers=headers, timeout=10)
                if resp.status_code != 200:
                    self.last_error = f"reddit meta http {resp.status_code}"
                    continue
                for child in resp.json().get("data", {}).get("children", []):
                    data = child.get("data", {})
                    if data.get("id"):
                        out[str(data["id"]).lower()] = data
            except (requests.RequestException, ValueError) as exc:
                self.last_error = f"reddit meta {type(exc).__name__}"
        return out


def judge_reddit(
    data: Optional[Dict[str, Any]],
    published_at: Optional[str] = None,
    now: Optional[datetime.date] = None,
) -> ThreadHealth:
    """Judge a Reddit thread from API data, or from the date when data is missing."""
    today = now or datetime.date.today()

    if not data:
        health = ThreadHealth(verified=False, kind="discussion")
        health.age_days = age_in_days(published_at, today)
        if health.age_days is None:
            health.reject = "no_date"
        elif health.age_days > REDDIT_ARCHIVE_DAYS:
            health.reject = "archived"
        else:
            health.commentable = True
            health.warnings.append("unverified_comment_state")
        return _apply_age_and_activity(health, "reddit")

    created = data.get("created_utc")
    age = None
    if created:
        created_day = datetime.datetime.fromtimestamp(float(created), tz=datetime.timezone.utc).date()
        age = (today - created_day).days
    health = ThreadHealth(
        verified=True,
        commentable=not (data.get("archived") or data.get("locked")),
        num_comments=int(data.get("num_comments") or 0),
        score=int(data.get("score") or 0),
        age_days=age,
    )
    title = str(data.get("title") or "")
    if data.get("archived"):
        health.reject = "archived"
    elif data.get("locked"):
        health.reject = "locked"
    elif data.get("removed_by_category") or str(data.get("selftext") or "").strip() in ("[removed]", "[deleted]"):
        health.reject = "removed"
    elif data.get("over_18"):
        health.reject = "nsfw"
    elif data.get("stickied") or data.get("distinguished"):
        health.reject = "mod_post"
    elif _PROMO_FLAIR.search(str(data.get("link_flair_text") or "")):
        health.reject = "promo_flair"
    elif not data.get("is_self", True) and "?" not in title:
        health.reject = "link_post"
    return _apply_age_and_activity(health, "reddit")


# ── Hacker News (Algolia) ───────────────────────────────────────────────────

def judge_hn(hit: Dict[str, Any], now: Optional[datetime.date] = None) -> ThreadHealth:
    today = now or datetime.date.today()
    age = age_in_days(str(hit.get("created_at") or ""), today)
    health = ThreadHealth(
        verified=True,
        commentable=True,
        num_comments=int(hit.get("num_comments") or 0),
        score=int(hit.get("points") or 0),
        age_days=age,
    )
    title = str(hit.get("title") or "")
    if re.match(r"\s*show hn\b", title, re.I):
        health.reject = "promo_post"
    return _apply_age_and_activity(health, "hackernews")


# ── GitHub ──────────────────────────────────────────────────────────────────

def judge_github(issue: Dict[str, Any], now: Optional[datetime.date] = None) -> ThreadHealth:
    today = now or datetime.date.today()
    health = ThreadHealth(
        verified=True,
        commentable=not issue.get("locked") and issue.get("state") == "open",
        num_comments=int(issue.get("comments") or 0),
        age_days=age_in_days(str(issue.get("created_at") or ""), today),
    )
    user = issue.get("user") or {}
    if issue.get("pull_request"):
        health.reject = "pull_request"
    elif issue.get("locked"):
        health.reject = "locked"
    elif issue.get("state") != "open":
        health.reject = "closed"
    elif str(user.get("type", "")).lower() == "bot":
        health.reject = "bot_author"
    elif str(issue.get("author_association", "")).upper() in ("OWNER", "MEMBER", "COLLABORATOR"):
        health.reject = "maintainer_post"
    return _apply_age_and_activity(health, "github")


# ── Generic web results ─────────────────────────────────────────────────────

# Hosts whose threads accept replies and hold real questions.
_DISCUSSION_HOSTS = (
    "news.ycombinator.com", "lobste.rs", "indiehackers.com", "stackoverflow.com",
    "serverfault.com", "superuser.com", "askubuntu.com", "stackexchange.com",
    "quora.com", "discourse.org", "producthunt.com",
)
_DISCUSSION_HOST_PREFIX = ("community.", "forum.", "forums.", "discuss.", "answers.", "ask.")
_DISCUSSION_PATH = re.compile(
    r"/(t/[^/]+/\d+|threads?/|topics?/|discussions?/|forums?/|questions?/|community/|answers?/|posts?/\d+)", re.I
)
_MARKETING_PATH = re.compile(
    r"/(pricing|features?|signup|sign-up|login|download|integrations?|alternatives?|compare|vs/|"
    r"products?|solutions?|customers?|case-stud|changelog|docs|about|contact|demo|tour|partners?)(/|$)",
    re.I,
)
_LISTICLE_TITLE = re.compile(
    r"\b(best|top)\s+\d*\s*[\w\s-]{0,40}\b(tools|software|apps|alternatives|platforms|options)\b"
    r"|\b\d+\s+(best|top|free|ways|tips|tools)\b|\bultimate guide\b|\bcomplete guide\b|\breview(s)?\b.*\bvs\b",
    re.I,
)
# These have their own harvest path, so the web path skips them.
_COVERED_ELSEWHERE = ("reddit.com", "redd.it", "x.com", "twitter.com", "news.ycombinator.com", "github.com")


def classify_web_result(
    url: str,
    title: str = "",
    exclude_hosts: Iterable[str] = (),
) -> ThreadHealth:
    """Accept only pages that look like open discussions. Reject the rest."""
    health = ThreadHealth(verified=False, kind="discussion")
    host = host_of(url)
    path = urllib.parse.urlsplit(url).path if url else ""

    if any(host == h or host.endswith("." + h) for h in _COVERED_ELSEWHERE):
        health.reject = "covered_elsewhere"
    elif any(h and (host == h or host.endswith("." + h)) for h in exclude_hosts):
        health.reject = "own_or_competitor_site"
    elif _LISTICLE_TITLE.search(title or ""):
        health.reject = "listicle"
    elif _MARKETING_PATH.search(path) and not any(host.endswith(h) for h in _DISCUSSION_HOSTS):
        health.reject = "marketing_page"
    else:
        is_discussion = (
            any(host == h or host.endswith("." + h) for h in _DISCUSSION_HOSTS)
            or host.startswith(_DISCUSSION_HOST_PREFIX)
            or bool(_DISCUSSION_PATH.search(path))
        )
        if not is_discussion:
            health.reject = "not_discussion"
        else:
            health.commentable = None  # unknown until a person opens the page
            health.warnings.append("unverified_comment_state")
    return health


# ── Promotion and spam ──────────────────────────────────────────────────────

_PROMO_PATTERNS = [
    r"\bshow hn\b",
    r"\b(i|we)\s+(just\s+)?(built|made|launched|released|shipped|created)\b",
    r"\b(check|try)\s+(it\s+)?out\b",
    r"\b(my|our)\s+(new\s+)?(app|tool|saas|startup|product|platform|newsletter|course)\b",
    r"\b(link in bio|use code|free trial|sign up|subscribe to|feedback (wanted|welcome))\b",
    r"\b\d+\s+(free\s+)?(tools|websites|apps|tips|ways|alternatives|resources|secrets|prompts)\b",
    r"\b(here are|here is)\s+\d+\b",
    r"\b(bookmark this|cheat sheet|steal my|mini-thread|save this post)\b",
    r"\b(how i made|how to make \$\d+)\b",
]
_PROMO_RE = [re.compile(p, re.I) for p in _PROMO_PATTERNS]


def is_promotional(title: str, text: str) -> bool:
    """True when the post reads as a seller announcing something."""
    blob = f"{title}\n{(text or '')[:1500]}"
    return any(p.search(blob) for p in _PROMO_RE)
