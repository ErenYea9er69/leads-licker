# -*- coding: utf-8 -*-
"""Read the comments of a thread and choose where a reply should go.

A reply can answer the post or one comment. `fetch_comments` returns a flat list
of comment dicts. `rank_targets` scores candidates with the rules in
skills/thread-engagement and returns ReplyTarget objects, best first.

Reddit's public JSON is rate limited and often blocked. On any failure the
functions return an empty list and a warning. The caller then falls back to a
post-level reply.
"""

from __future__ import annotations

import datetime
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from agent_reach.discovery.models import BusinessProfile, ReplyTarget
from agent_reach.discovery.security import sanitize
from agent_reach.discovery.thread_check import USER_AGENT, reddit_post_id, youtube_video_id

log = logging.getLogger("agent_reach.discovery")

_ASKS = re.compile(
    r"\?|\b(?:what do you use|any (?:tool|app|software|recommendation|rec|name|suggestion)s?|"
    r"looking for|also looking|recommend|is there (?:a|an|any)|link\b|name\b|how do (?:i|you|we))",
    re.I,
)
_HOSTILE = re.compile(r"\b(?:idiot|stupid|shut up|stfu|lol no|get lost|bot\b)", re.I)
_URL = re.compile(r"https?://\S+")
_GITHUB_ISSUE = re.compile(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)")
_HN_ID = re.compile(r"[?&]id=(\d+)")


def _age_hours(created_utc: Optional[float]) -> Optional[float]:
    if not created_utc:
        return None
    return max(0.0, (time.time() - float(created_utc)) / 3600.0)


def _flatten_reddit(children: List[Dict[str, Any]], depth: int, op: str, out: List[Dict[str, Any]]) -> None:
    for child in children:
        if child.get("kind") != "t1":
            continue
        d = child.get("data") or {}
        replies = d.get("replies")
        reply_children = []
        if isinstance(replies, dict):
            reply_children = (replies.get("data") or {}).get("children", [])
        out.append({
            "id": d.get("id", ""),
            "author": d.get("author") or "",
            "body": d.get("body") or "",
            "score": int(d.get("score") or 0),
            "depth": depth,
            "created_utc": d.get("created_utc"),
            "is_submitter": bool(d.get("is_submitter")) or (d.get("author") == op and bool(op)),
            "distinguished": d.get("distinguished"),
            "stickied": bool(d.get("stickied")),
            "reply_count": len([c for c in reply_children if c.get("kind") == "t1"]),
        })
        _flatten_reddit(reply_children, depth + 1, op, out)


def fetch_reddit_comments(url: str, session: Optional[requests.Session] = None, limit: int = 80) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """Return (post, comments, warnings) from Reddit's public JSON."""
    session = session or requests.Session()
    pid = reddit_post_id(url)
    if not pid:
        return {}, [], ["Not a Reddit post URL."]
    query: Dict[str, Any] = {"limit": min(limit * 2, 300), "raw_json": 1, "sort": "top"}
    try:
        resp = session.get(
            f"https://www.reddit.com/comments/{pid}.json",
            params=query,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            timeout=12,
        )
    except requests.RequestException as exc:
        return {}, [], [f"Reddit comments unavailable: {type(exc).__name__}"]
    if resp.status_code != 200:
        return {}, [], [f"Reddit comments unavailable: http {resp.status_code}"]
    try:
        listing = resp.json()
        post = ((listing[0].get("data") or {}).get("children") or [{}])[0].get("data") or {}
        children = (listing[1].get("data") or {}).get("children", [])
    except (ValueError, IndexError, AttributeError, TypeError):
        return {}, [], ["Reddit comments unavailable: unexpected response."]
    flat: List[Dict[str, Any]] = []
    _flatten_reddit(children, 0, post.get("author") or "", flat)
    post_info = {
        "id": post.get("id"), "author": post.get("author"), "title": post.get("title"),
        "selftext": post.get("selftext"), "num_comments": post.get("num_comments"),
        "locked": bool(post.get("locked")), "archived": bool(post.get("archived")),
        "created_utc": post.get("created_utc"),
    }
    return post_info, flat[:limit], []


def _flatten_hn(node: Dict[str, Any], depth: int, op: str, out: List[Dict[str, Any]]) -> None:
    for child in node.get("children") or []:
        text = re.sub(r"<[^>]+>", " ", child.get("text") or "")
        out.append({
            "id": str(child.get("id", "")),
            "author": child.get("author") or "",
            "body": re.sub(r"\s+", " ", text).strip(),
            "score": 0,
            "depth": depth,
            "created_utc": child.get("created_at_i"),
            "is_submitter": child.get("author") == op and bool(op),
            "distinguished": None,
            "stickied": False,
            "reply_count": len(child.get("children") or []),
        })
        _flatten_hn(child, depth + 1, op, out)


def fetch_hn_comments(url: str, session: Optional[requests.Session] = None, limit: int = 80) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    session = session or requests.Session()
    m = _HN_ID.search(url or "")
    if not m:
        return {}, [], ["Not a Hacker News item URL."]
    try:
        resp = session.get(f"https://hn.algolia.com/api/v1/items/{m.group(1)}", headers={"User-Agent": USER_AGENT}, timeout=12)
        if resp.status_code != 200:
            return {}, [], [f"HN comments unavailable: http {resp.status_code}"]
        node = resp.json()
    except (requests.RequestException, ValueError) as exc:
        return {}, [], [f"HN comments unavailable: {type(exc).__name__}"]
    flat: List[Dict[str, Any]] = []
    _flatten_hn(node, 0, node.get("author") or "", flat)
    post = {"id": node.get("id"), "author": node.get("author"), "title": node.get("title"),
            "selftext": re.sub(r"<[^>]+>", " ", node.get("text") or ""), "num_comments": len(flat)}
    return post, flat[:limit], []


def fetch_github_comments(url: str, session: Optional[requests.Session] = None, limit: int = 50) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    session = session or requests.Session()
    m = _GITHUB_ISSUE.search(url or "")
    if not m:
        return {}, [], ["Not a GitHub issue URL."]
    owner, repo, num = m.groups()
    base = f"https://api.github.com/repos/{owner}/{repo}/issues/{num}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    try:
        issue = session.get(base, headers=headers, timeout=12)
        comments = session.get(f"{base}/comments", params={"per_page": min(limit, 100)}, headers=headers, timeout=12)
        if issue.status_code != 200 or comments.status_code != 200:
            return {}, [], [f"GitHub comments unavailable: http {issue.status_code}/{comments.status_code}"]
        idata, cdata = issue.json(), comments.json()
    except (requests.RequestException, ValueError) as exc:
        return {}, [], [f"GitHub comments unavailable: {type(exc).__name__}"]
    op = (idata.get("user") or {}).get("login") or ""
    flat = []
    for c in cdata:
        author = (c.get("user") or {}).get("login") or ""
        created = None
        try:
            created = datetime.datetime.fromisoformat((c.get("created_at") or "").replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
        flat.append({
            "id": str(c.get("id", "")), "author": author, "body": c.get("body") or "", "score": 0, "depth": 0,
            "created_utc": created, "is_submitter": author == op and bool(op), "distinguished": None,
            "stickied": False, "reply_count": 0,
        })
    post = {"id": idata.get("number"), "author": op, "title": idata.get("title"), "selftext": idata.get("body") or "",
            "num_comments": idata.get("comments"), "locked": bool(idata.get("locked"))}
    return post, flat[:limit], []


def fetch_youtube_comments(
    url: str, session: Optional[requests.Session] = None, limit: int = 50, storage: Any = None
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    """A video as the post, its top comments as targets. The post's `context` holds a transcript excerpt."""
    from agent_reach.discovery import youtube

    vid = youtube_video_id(url)
    if not vid:
        return {}, [], ["Not a YouTube video URL."]
    api = youtube.YouTubeAPI(session, storage)
    warnings: List[str] = []
    prefs = (storage.get_setting("reply_preferences", {}) or {}) if storage is not None else {}
    lang = str(prefs.get("language") or "en")
    if not api.available():
        return {}, [], ["YouTube comments need YOUTUBE_API_KEY. Reply at video level, or set the key."]
    try:
        video = api.videos([vid]).get(vid)
        if not video:
            return {}, [], ["YouTube did not return this video. It may be private or removed."]
        channel_id = (video.get("snippet") or {}).get("channelId") or ""
        try:
            flat = youtube.flatten_comments(api.comment_threads(vid, min(limit, 100)), channel_id)
        except youtube.YouTubeError as exc:
            if exc.code != "comments_disabled":
                raise
            return {}, [], [str(exc)]
    except youtube.YouTubeError as exc:
        return {}, [], [f"YouTube comments unavailable: {exc}"]
    title = str((video.get("snippet") or {}).get("title") or "")
    tr = youtube.fetch_transcript(vid, [lang], translate_to=lang)
    context = ""
    if tr.get("ok"):
        context = youtube.transcript_note(tr) + "\n" + youtube.excerpt(tr["segments"], title)
    else:
        warnings.append(f"No transcript: {tr.get('message')}")
    return youtube.post_info(video, context), flat[:limit], warnings


def fetch_comments(
    url: str, session: Optional[requests.Session] = None, limit: int = 80, storage: Any = None
) -> Tuple[Dict[str, Any], List[Dict[str, Any]], List[str]]:
    low = (url or "").lower()
    if "youtube.com" in low or "youtu.be" in low:
        return fetch_youtube_comments(url, session, limit, storage)
    if "reddit.com" in low or "redd.it" in low:
        return fetch_reddit_comments(url, session, limit)
    if "news.ycombinator.com" in low:
        return fetch_hn_comments(url, session, limit)
    if "github.com" in low:
        return fetch_github_comments(url, session, limit)
    return {}, [], ["Comment reading is not supported for this site. Reply at post level."]


def _relevance(text: str, profile: Optional[BusinessProfile]) -> float:
    if not profile:
        return 0.0
    words = set(re.findall(r"[a-z]{4,}", text.lower()))
    phrases = list(profile.pain_vocabulary) + list(profile.problems_solved) + list(profile.customer_frustrations)
    best = 0.0
    for ph in phrases:
        need = set(re.findall(r"[a-z]{4,}", ph.lower()))
        if need:
            best = max(best, len(need & words) / len(need))
    return best


def rank_targets(
    post: Dict[str, Any],
    comments: List[Dict[str, Any]],
    profile: Optional[BusinessProfile] = None,
    post_answered: bool = False,
    limit: int = 5,
) -> List[ReplyTarget]:
    """Score reply targets. The table matches skills/thread-engagement."""
    targets: List[ReplyTarget] = []
    context = sanitize(post.get("context") or "", 900)
    thread_closed = bool(post.get("locked") or post.get("archived"))
    n_comments = int(post.get("num_comments") or len(comments) or 0)

    if not thread_closed:
        base = 5.0
        reason = "The post asks a question and no comment answers the exact constraint."
        if post_answered:
            base -= 3
            reason = "The post has an answer already. Reply only if you add a missing piece."
        if n_comments >= 80:
            base -= 3
            reason += " The thread is crowded."
        targets.append(ReplyTarget(
            target_kind="post", target_author=post.get("author") or "",
            target_text=sanitize((post.get("title") or "") + ". " + (post.get("selftext") or ""), 300)[:300],
            reason=reason, score=base, context=context,
        ))
    if thread_closed:
        return []

    for c in comments:
        body = sanitize(c.get("body") or "", 1500).strip()
        words = len(body.split())
        author = c.get("author") or ""
        if not body or body in ("[deleted]", "[removed]") or author in ("[deleted]", "AutoModerator"):
            continue
        if c.get("distinguished") or c.get("stickied") or (c.get("score") or 0) < 0:
            continue
        if _HOSTILE.search(body):
            continue
        asks = bool(_ASKS.search(body))
        if words < 8 and not asks:
            continue
        has_url = bool(_URL.search(body))
        age = _age_hours(c.get("created_utc"))
        score = 0.0
        reason = ""
        if c.get("is_submitter") and asks:
            score, reason = 7.0, "The author asks a follow-up question and is present in the thread."
        elif asks and (c.get("reply_count") or 0) == 0:
            score, reason = 6.0, "A commenter asks for a tool or method and nobody has answered."
        elif asks:
            score, reason = 3.5, "A commenter asks a question that already has replies."
        else:
            continue
        if has_url and not asks:
            score -= 4
        if age is not None and age > 72:
            score -= 3
            reason += " The comment is older than 3 days."
        if (c.get("depth") or 0) >= 3:
            score -= 2
        rel = _relevance(body, profile)
        score += 2.0 * rel
        if rel >= 0.5:
            reason += " It matches a problem the product solves."
        if score <= 0:
            continue
        targets.append(ReplyTarget(
            target_kind="comment", target_comment_id=str(c.get("id") or ""), target_author=author,
            target_text=body[:300], reason=reason.strip(), score=round(score, 2),
            depth=int(c.get("depth") or 0), age_hours=round(age, 1) if age is not None else None, context=context,
        ))
    targets.sort(key=lambda t: -t.score)
    return targets[:limit]
