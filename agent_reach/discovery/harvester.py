# -*- coding: utf-8 -*-
"""Community harvester for Reddit, Hacker News, Quora, X, GitHub and the open web.

Every candidate passes thread verification before it becomes a DiscoveredItem.
The harvester never invents data. When a source fails it logs the failure,
counts it in `diagnostics`, and returns nothing.
"""

from __future__ import annotations

import datetime
import html
import logging
import re
import time
import urllib.parse
from collections import Counter
from typing import Any, Dict, Iterable, List, Optional

import requests

from agent_reach.discovery.models import DiscoveredItem, SearchQuery
from agent_reach.discovery.search_backends import DuckDuckGoSearch, SearchChain
from agent_reach.discovery.storage import DiscoveryStorage
from agent_reach.discovery.thread_check import (
    PLATFORM_MAX_AGE_DAYS,
    USER_AGENT,
    RedditMeta,
    ThreadHealth,
    age_in_days,
    canonical_url,
    classify_web_result,
    host_of,
    is_promotional,
    judge_github,
    judge_hn,
    judge_reddit,
    reddit_post_id,
)

log = logging.getLogger("agent_reach.discovery")

_SUB_RE = re.compile(r"^r/[A-Za-z0-9_]{3,21}$")
_QUORA_SKIP = re.compile(r"^/(profile|topic|q|unanswered|search|spaces?)(/|$)", re.I)
_TWITTER_INDEXERS = ("threadreaderapp.com", "en.rattibha.com")
_SNOWFLAKE_EPOCH_MS = 1288834974657
_TAG_RE = re.compile(r"<[^>]+>")


def _clean_query(query: str) -> str:
    return query.replace('"', "").replace("'", "").strip()


def _strip_html(raw: str) -> str:
    text = re.sub(r"<p>|<br\s*/?>", "\n", raw or "")
    return html.unescape(_TAG_RE.sub("", text)).strip()


class CommunityHarvester:
    """Runs one search query and returns verified, reply-ready threads."""

    def __init__(
        self,
        storage: Optional[DiscoveryStorage] = None,
        reddit_meta: Optional[RedditMeta] = None,
        session: Optional[requests.Session] = None,
    ):
        self.storage = storage or DiscoveryStorage()
        self.session = session or requests.Session()
        if reddit_meta:
            self.reddit_meta = reddit_meta
        else:
            posting = self.storage.get_setting("posting_settings", {}) or {}
            r_id = posting.get("reddit_client_id")
            r_sec = posting.get("reddit_client_secret")
            self.reddit_meta = RedditMeta(client_id=r_id, client_secret=r_sec, session=self.session)
        self.exclude_hosts: List[str] = []   # the user's own site and competitor sites
        self._diagnostics: Counter = Counter()
        self.search_chain = SearchChain(self.session, self._diagnostics)

    @property
    def diagnostics(self) -> Counter:
        return self._diagnostics

    @diagnostics.setter
    def diagnostics(self, value: Counter) -> None:
        self._diagnostics = value
        self.search_chain.diagnostics = value

    # ── Routing ──

    def set_exclusions(self, hosts: Iterable[str]) -> None:
        self.exclude_hosts = [h.lower() for h in hosts if h]

    def execute_query(self, query: SearchQuery, limit: int = 5) -> List[DiscoveredItem]:
        platform = query.platform.lower()
        try:
            if platform == "reddit":
                return self.search_reddit(query.query, subreddit=query.target_community, limit=limit)
            if platform == "hackernews":
                return self.search_hackernews(query.query, limit=limit)
            if platform == "quora":
                return self.search_quora(query.query, limit=limit)
            if platform in ("twitter", "x"):
                return self.search_twitter(query.query, limit=limit)
            if platform == "github":
                return self.search_github(query.query, limit=limit)
            if platform == "youtube":
                return self.search_youtube(query.query, limit=limit)
            return self.search_web(query.query, limit=limit)
        except Exception as exc:  # one bad query must not stop the campaign
            log.exception("harvest failed for %s query %r", platform, query.query)
            self.diagnostics[f"error:{type(exc).__name__}"] += 1
            return []

    # ── Shared helpers ──

    def _reject(self, code: str) -> None:
        self.diagnostics[f"rejected:{code}"] += 1

    def _search(self, query: str, limit: int, days: Optional[int] = None) -> List[Dict[str, Any]]:
        """Keyed providers first, then Exa, then DuckDuckGo. Returns [] and counts failures."""
        return self.search_chain.search(query, limit, days)

    def _duckduckgo(self, query: str, limit: int) -> List[Dict[str, Any]]:
        """Kept for older callers. Use `_search`."""
        try:
            return DuckDuckGoSearch(self.session).search(query, limit)
        except Exception as exc:
            log.warning("DuckDuckGo failed: %s", type(exc).__name__)
            self.diagnostics["search_error:duckduckgo"] += 1
            return []

    def _keep(self, item: DiscoveredItem, health: ThreadHealth) -> Optional[DiscoveredItem]:
        item.thread_health = health.to_dict()
        if not self.storage.save_discovered_item(item):
            self._reject("duplicate")
            return None
        return item

    # ── Reddit ──

    def search_reddit(self, query: str, subreddit: Optional[str] = None, limit: int = 5) -> List[DiscoveredItem]:
        sub = subreddit.strip() if subreddit and _SUB_RE.match(subreddit.strip()) else None
        scope = f"site:reddit.com/{sub}" if sub else "site:reddit.com"
        results = self._search(f"{scope} {_clean_query(query)}", limit * 3, days=PLATFORM_MAX_AGE_DAYS["reddit"])

        candidates, seen = [], set()
        for res in results:
            url = res.get("url", "")
            pid = reddit_post_id(url)
            if not pid or "reddit.com" not in host_of(url) or pid in seen:
                self._reject("not_reddit_post")
                continue
            seen.add(pid)
            canon = canonical_url(url)
            if self.storage.is_url_discovered(canon):
                self._reject("duplicate")
                continue
            candidates.append((pid, canon, res))

        metas = self.reddit_meta.fetch([c[0] for c in candidates]) if candidates else {}
        if candidates and not metas:
            self.diagnostics["reddit_meta_unavailable"] += 1

        items: List[DiscoveredItem] = []
        for pid, canon, res in candidates:
            data = metas.get(pid)
            health = judge_reddit(data, published_at=res.get("published_at"))
            if health.reject:
                self._reject(health.reject)
                continue
            title = (data or {}).get("title") or re.split(r"\s+[:\-|]\s+(?:Reddit|r/)", res.get("title") or query)[0].strip()
            content = (res.get("text") or "").strip() or (data or {}).get("selftext", "")
            if is_promotional(title, content):
                self._reject("promotional")
                continue
            created = (data or {}).get("created_utc")
            published = (
                datetime.datetime.fromtimestamp(float(created), tz=datetime.timezone.utc).strftime("%Y-%m-%d")
                if created else (res.get("published_at") or "")[:10]
            )
            detected = (data or {}).get("subreddit")
            item = DiscoveredItem(
                url=canon,
                platform="reddit",
                community=f"r/{detected}" if detected else (sub or "reddit"),
                author=(data or {}).get("author") or res.get("author") or "",
                published_at=published,
                title=title,
                content=f"{title}\n\n{content}"[:6000],
                raw_data={"source": "exa", "has_api_meta": bool(data)},
            )
            kept = self._keep(item, health)
            if kept:
                items.append(kept)
            if len(items) >= limit:
                break

        if not items and not results:
            items = self._reddit_direct(query, sub, limit)
        return items

    def _reddit_direct(self, query: str, sub: Optional[str], limit: int) -> List[DiscoveredItem]:
        """Fallback: Reddit's own search. Often blocked without OAuth."""
        q = urllib.parse.quote(query)
        if sub:
            url = f"https://www.reddit.com/{sub}/search.json?q={q}&restrict_sr=1&sort=relevance&limit={limit * 3}&raw_json=1"
        else:
            url = f"https://www.reddit.com/search.json?q={q}&sort=relevance&limit={limit * 3}&raw_json=1"
        try:
            resp = self.session.get(url, headers={"User-Agent": USER_AGENT}, timeout=10)
            if resp.status_code != 200:
                self.diagnostics[f"search_error:reddit_http_{resp.status_code}"] += 1
                return []
            children = resp.json().get("data", {}).get("children", [])
        except (requests.RequestException, ValueError) as exc:
            log.warning("Reddit direct search failed: %s", type(exc).__name__)
            self.diagnostics["search_error:reddit"] += 1
            return []

        items: List[DiscoveredItem] = []
        for child in children:
            data = child.get("data", {})
            canon = canonical_url(f"https://reddit.com{data.get('permalink', '')}")
            if not data.get("id") or self.storage.is_url_discovered(canon):
                continue
            health = judge_reddit(data)
            if health.reject:
                self._reject(health.reject)
                continue
            title, body = data.get("title", ""), data.get("selftext", "")
            if is_promotional(title, body):
                self._reject("promotional")
                continue
            created = datetime.datetime.fromtimestamp(float(data["created_utc"]), tz=datetime.timezone.utc)
            item = DiscoveredItem(
                url=canon,
                platform="reddit",
                community=f"r/{data.get('subreddit', 'reddit')}",
                author=data.get("author", ""),
                published_at=created.strftime("%Y-%m-%d"),
                title=title,
                content=f"{title}\n\n{body}".strip()[:6000],
                raw_data={"source": "reddit_search"},
            )
            kept = self._keep(item, health)
            if kept:
                items.append(kept)
            if len(items) >= limit:
                break
        return items

    # ── Hacker News (Algolia) ──

    def search_hackernews(self, query: str, limit: int = 5) -> List[DiscoveredItem]:
        max_age = PLATFORM_MAX_AGE_DAYS["hackernews"]
        since = int(time.time()) - max_age * 86400
        items: List[DiscoveredItem] = []
        for tag in ("ask_hn", "story"):
            params = {
                "query": _clean_query(query),
                "tags": tag,
                "numericFilters": f"created_at_i>{since}",
                "hitsPerPage": limit * 3,
            }
            try:
                resp = self.session.get(
                    "https://hn.algolia.com/api/v1/search",
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=10,
                )
                if resp.status_code != 200:
                    self.diagnostics[f"search_error:hn_http_{resp.status_code}"] += 1
                    continue
                hits = resp.json().get("hits", [])
            except (requests.RequestException, ValueError) as exc:
                log.warning("HN search failed: %s", type(exc).__name__)
                self.diagnostics["search_error:hn"] += 1
                continue

            for hit in hits:
                oid = hit.get("objectID")
                title = hit.get("title") or ""
                body = _strip_html(hit.get("story_text") or "")
                if not oid or not title:
                    continue
                canon = f"https://news.ycombinator.com/item?id={oid}"
                if self.storage.is_url_discovered(canon):
                    self._reject("duplicate")
                    continue
                health = judge_hn(hit)
                if not health.reject and tag == "story" and hit.get("url") and not body:
                    health.reject = "link_post"   # a shared link, not a question
                if health.reject:
                    self._reject(health.reject)
                    continue
                if is_promotional(title, body):
                    self._reject("promotional")
                    continue
                item = DiscoveredItem(
                    url=canon,
                    platform="hackernews",
                    community="Hacker News",
                    author=hit.get("author") or "",
                    published_at=(hit.get("created_at") or "")[:10],
                    title=title,
                    content=f"{title}\n\n{body}".strip()[:6000],
                    raw_data={"points": hit.get("points"), "tag": tag},
                )
                kept = self._keep(item, health)
                if kept:
                    items.append(kept)
                if len(items) >= limit:
                    return items
        return items

    # ── Quora ──

    def search_quora(self, query: str, limit: int = 5) -> List[DiscoveredItem]:
        results = self._search(f"site:quora.com {_clean_query(query)}", limit * 3)
        items: List[DiscoveredItem] = []
        for res in results:
            url = res.get("url", "")
            if "quora.com" not in host_of(url) or _QUORA_SKIP.match(urllib.parse.urlsplit(url).path or "/"):
                self._reject("not_quora_question")
                continue
            canon = canonical_url(url)
            if self.storage.is_url_discovered(canon):
                self._reject("duplicate")
                continue
            title = (res.get("title") or query).replace(" - Quora", "").strip()
            content = (res.get("text") or "").strip()
            if is_promotional(title, content):
                self._reject("promotional")
                continue
            published = (res.get("published_at") or "")[:10]
            health = ThreadHealth(verified=False, kind="discussion", age_days=age_in_days(published))
            health.warnings.append("unverified_comment_state")
            if not published:
                health.warnings.append("no_date")
            elif health.age_days is not None and health.age_days > PLATFORM_MAX_AGE_DAYS["quora"]:
                self._reject("too_old")
                continue
            item = DiscoveredItem(
                url=canon, platform="quora", community="Quora", author=res.get("author") or "",
                published_at=published, title=title, content=f"{title}\n\n{content}"[:6000],
                raw_data={"source": "exa"},
            )
            kept = self._keep(item, health)
            if kept:
                items.append(kept)
            if len(items) >= limit:
                break
        return items

    # ── X / Twitter ──

    def search_twitter(self, query: str, limit: int = 5) -> List[DiscoveredItem]:
        """Weak source. Thread indexers mostly list creators' threads, not customers asking for help."""
        clean = _clean_query(query)
        results: List[Dict[str, Any]] = []
        for site in _TWITTER_INDEXERS:
            results.extend(self._search(f"site:{site} {clean}", limit * 2))
        max_age = PLATFORM_MAX_AGE_DAYS["twitter"]
        items: List[DiscoveredItem] = []
        seen = set()
        for res in results:
            m = re.search(r"/(?:thread|status)/(\d+)", res.get("url", ""))
            if not m or m.group(1) in seen:
                continue
            tid = int(m.group(1))
            seen.add(m.group(1))
            posted = datetime.datetime.fromtimestamp(
                ((tid >> 22) + _SNOWFLAKE_EPOCH_MS) / 1000, tz=datetime.timezone.utc
            )
            age = (datetime.datetime.now(datetime.timezone.utc) - posted).days
            if age > max_age:
                self._reject("too_old")
                continue
            title = re.sub(r"^(?:Thread by|Thread on|Post by)\s*@?\w*[:\s-]*", "", res.get("title") or "", flags=re.I)
            title = re.sub(r"\s*[-|]\s*(?:Thread Reader App|Rattibha).*$", "", title, flags=re.I).strip()
            content = (res.get("text") or "").strip()
            if is_promotional(title, content):
                self._reject("promotional")
                continue
            canon = f"https://x.com/i/status/{tid}"
            if self.storage.is_url_discovered(canon):
                self._reject("duplicate")
                continue
            handle = re.search(r"@([A-Za-z0-9_]{1,15})", f"{res.get('title', '')} {content}")
            health = ThreadHealth(verified=False, commentable=True, age_days=age, warnings=["indexer_source"])
            item = DiscoveredItem(
                url=canon, platform="twitter", community="X / Twitter",
                author=f"@{handle.group(1)}" if handle else "",
                published_at=posted.strftime("%Y-%m-%d"),
                title=title or content[:100], content=f"{title}\n\n{content}"[:6000],
                raw_data={"source": "indexer"},
            )
            kept = self._keep(item, health)
            if kept:
                items.append(kept)
            if len(items) >= limit:
                break
        return items

    # ── Open web: discussions only ──

    def search_web(self, query: str, limit: int = 5) -> List[DiscoveredItem]:
        results = self._search(_clean_query(query), limit * 4)
        items: List[DiscoveredItem] = []
        for res in results:
            url = res.get("url", "")
            if not url:
                continue
            title = res.get("title") or ""
            health = classify_web_result(url, title, self.exclude_hosts)
            published = (res.get("published_at") or "")[:10]
            health.age_days = age_in_days(published)
            if not health.reject:
                if not published:
                    health.warnings.append("no_date")
                elif health.age_days is not None and health.age_days > PLATFORM_MAX_AGE_DAYS["web"]:
                    health.reject = "too_old"
            if health.reject:
                self._reject(health.reject)
                continue
            canon = canonical_url(url)
            if self.storage.is_url_discovered(canon):
                self._reject("duplicate")
                continue
            content = (res.get("text") or "").strip()
            if is_promotional(title, content):
                self._reject("promotional")
                continue
            item = DiscoveredItem(
                url=canon, platform="web", community=host_of(url),
                author=res.get("author") or "", published_at=published,
                title=title, content=f"{title}\n\n{content}"[:6000], raw_data={"source": "exa"},
            )
            kept = self._keep(item, health)
            if kept:
                items.append(kept)
            if len(items) >= limit:
                break
        return items

    # ── YouTube ──

    def search_youtube(self, query: str, limit: int = 5) -> List[DiscoveredItem]:
        """Videos whose comments hold the customers. Needs YOUTUBE_API_KEY for comment counts and comments.

        Without a key the search runs through the web search chain. Those videos stay unverified and carry
        no comments. The transcript, when the video has one, is read in the owner's language.
        """
        from agent_reach.discovery import youtube as yt
        from agent_reach.discovery.thread_check import youtube_video_id

        clean = _clean_query(query)
        lang = str((self.storage.get_setting("reply_preferences", {}) or {}).get("language") or "en")
        max_age = PLATFORM_MAX_AGE_DAYS["youtube"]
        api = yt.YouTubeAPI(self.session, self.storage)
        found: List[Dict[str, Any]] = []   # {"id", "title", "published_at", "channel"}
        metas: Dict[str, Dict[str, Any]] = {}
        if api.available():
            try:
                for hit in api.search(clean, limit * 3, days=max_age, language=lang):
                    vid = (hit.get("id") or {}).get("videoId")
                    snip = hit.get("snippet") or {}
                    if vid:
                        found.append({"id": vid, "title": snip.get("title") or "", "published_at": snip.get("publishedAt"), "channel": snip.get("channelTitle") or ""})
                metas = api.videos([f["id"] for f in found])
            except yt.YouTubeError as exc:
                log.warning("YouTube API failed: %s", str(exc)[:160])
                self.diagnostics[f"youtube_api:{exc.code}"] += 1
                found, metas = [], {}
        if not found:   # no key, or the API failed: the web search chain still lists videos
            for res in self._search(f"site:youtube.com/watch {clean}", limit * 3, days=max_age):
                vid = youtube_video_id(res.get("url", ""))
                if vid:
                    found.append({"id": vid, "title": re.sub(r"\s*-\s*YouTube$", "", res.get("title") or ""), "published_at": res.get("published_at"), "channel": res.get("author") or "", "text": res.get("text") or ""})

        items: List[DiscoveredItem] = []
        seen = set()
        for hit in found:
            vid = hit["id"]
            if vid in seen:
                continue
            seen.add(vid)
            canon = f"https://youtube.com/watch?v={vid}"
            if self.storage.is_url_discovered(canon):
                self._reject("duplicate")
                continue
            meta = metas.get(vid)
            health = yt.judge_youtube(meta, hit.get("published_at"))
            if not health.reject and not yt.same_language(yt.video_language(meta or {}), lang):
                health.reject = "language_mismatch"
            snip = (meta or {}).get("snippet") or {}
            title = snip.get("title") or hit["title"]
            description = (snip.get("description") or hit.get("text") or "").strip()
            if not health.reject and is_promotional(title, description):
                health.reject = "promotional"
            if health.reject:
                self._reject(health.reject)
                continue

            parts = [title, description[:600]]
            transcript: Dict[str, Any] = {}
            tr = yt.fetch_transcript(vid, [lang], translate_to=lang)
            if tr.get("ok"):
                self.diagnostics["youtube_transcript_ok"] += 1
                transcript = {k: tr[k] for k in ("language_code", "is_generated", "translated", "translated_to", "characters")}
                parts.append(yt.transcript_note(tr) + "\n" + yt.excerpt(tr["segments"], clean))
            else:
                self.diagnostics[f"youtube_transcript:{tr.get('error')}"] += 1
            if api.available() and health.verified and (health.num_comments or 0) > 0:
                try:
                    flat = yt.flatten_comments(api.comment_threads(vid, 8), snip.get("channelId") or "")
                    top = [f"- {c['author']}: {c['body'][:220]}" for c in flat if c["depth"] == 0][:6]
                    if top:
                        parts.append("Top comments:\n" + "\n".join(top))
                except yt.YouTubeError as exc:
                    if exc.code == "comments_disabled":
                        self._reject("comments_disabled")
                        continue
                    self.diagnostics[f"youtube_comments:{exc.code}"] += 1
            item = DiscoveredItem(
                url=canon, platform="youtube", community=snip.get("channelTitle") or hit.get("channel") or "YouTube",
                author=snip.get("channelTitle") or hit.get("channel") or "",
                published_at=str(snip.get("publishedAt") or hit.get("published_at") or "")[:10],
                title=title, content="\n\n".join(p for p in parts if p)[:6000],
                raw_data={"source": "api" if meta else "search", "video_id": vid, "channel_id": snip.get("channelId") or "",
                          "language": yt.video_language(meta or {}), "transcript": transcript},
            )
            kept = self._keep(item, health)
            if kept:
                items.append(kept)
            if len(items) >= limit:
                break
        return items

    # ── GitHub issues ──

    def search_github(self, query: str, limit: int = 5) -> List[DiscoveredItem]:
        import os

        since = (datetime.date.today() - datetime.timedelta(days=PLATFORM_MAX_AGE_DAYS["github"])).isoformat()
        clean = re.sub(r"\b(is|state|created):\S+", "", query).replace('"', "").strip()
        q = f"{clean} is:issue is:open archived:false created:>={since}"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
        token = (
            os.getenv("GITHUB_TOKEN")
            or os.getenv("GH_TOKEN")
            or (self.storage.get_setting("posting_settings", {}) or {}).get("github_token")
        )
        if not token:
            try:
                from agent_reach.config import Config

                token = Config(read_only=True).get("github_token")
            except Exception:
                pass
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            resp = self.session.get(
                "https://api.github.com/search/issues",
                params={"q": q, "per_page": str(limit * 3), "sort": "updated"},
                headers=headers,
                timeout=10,
            )
            if resp.status_code != 200:
                self.diagnostics[f"search_error:github_http_{resp.status_code}"] += 1
                return []
            issues = resp.json().get("items", [])
        except (requests.RequestException, ValueError) as exc:
            log.warning("GitHub search failed: %s", type(exc).__name__)
            self.diagnostics["search_error:github"] += 1
            return []

        items: List[DiscoveredItem] = []
        for issue in issues:
            canon = canonical_url(issue.get("html_url", ""))
            if not canon or self.storage.is_url_discovered(canon):
                self._reject("duplicate")
                continue
            health = judge_github(issue)
            if health.reject:
                self._reject(health.reject)
                continue
            title, body = issue.get("title", ""), issue.get("body") or ""
            if is_promotional(title, body):
                self._reject("promotional")
                continue
            item = DiscoveredItem(
                url=canon, platform="github",
                community=issue.get("repository_url", "").replace("https://api.github.com/repos/", ""),
                author=(issue.get("user") or {}).get("login", ""),
                published_at=(issue.get("created_at") or "")[:10],
                title=title, content=f"{title}\n\n{body}".strip()[:6000],
                raw_data={"comments": issue.get("comments", 0)},
            )
            kept = self._keep(item, health)
            if kept:
                items.append(kept)
            if len(items) >= limit:
                break
        return items
