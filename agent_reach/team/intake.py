# -*- coding: utf-8 -*-
"""The CEO's interview with the owner, and the work the CEO starts while the owner answers.

The owner does not wait for a form. The CEO asks one or two questions at a time. As soon as it knows the
product and the target users, it starts the search in the background. The owner keeps answering questions
about accounts, voice, language and rules while the threads come in. Nothing found this way is scored or
drafted yet. The later `find_customers` plan claims those threads through its own harvest step.

The CEO never invents an answer. Facts are the owner's words. A search query comes from those words.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from agent_reach.discovery.models import BusinessProfile
from agent_reach.discovery.security import sanitize

log = logging.getLogger("agent_reach.team")

STATE_KEY = "intake_state"
MAX_RUNS = 3
QUERIES_PER_PLATFORM = 4
THREADS_PER_QUERY = 5
DEFAULT_PLATFORMS = ["reddit", "hackernews", "web"]
_LOCK = threading.Lock()
_RUNNING: set = set()   # run ids with a live thread in this process


@dataclass(frozen=True)
class Field:
    key: str
    ask: str
    why: str
    required: bool = False
    market: bool = True   # a question about the market or the product. False means the search does not need it.


FIELDS: Tuple[Field, ...] = (
    Field("product", "What does your product do? One or two sentences in your own words.",
          "The search starts from this.", required=True),
    Field("target_users", "Who has the problem you solve? Their role, the kind of company, the size.",
          "The search looks for these people.", required=True),
    Field("problems", "What do those people complain about? Write it the way they would say it.",
          "Their words become the search phrases. This is the biggest gain in result quality."),
    Field("platforms", "Where do they talk? Reddit, YouTube, X, Hacker News, GitHub, forums, other places?",
          "Decides which sources the CEO searches."),
    Field("competitors", "Which tools or methods do they use today instead of yours?",
          "People who compare alternatives are the closest buyers."),
    Field("site", "Is there a link to your site or product page?",
          "The analyst reads it to build the business profile.", market=False),
    Field("accounts", "Which accounts do you own? Give platform and handle. You can link several per platform.",
          "Each account gets its own voice and daily limit. Without one, replies use the lowest pitch level.", market=False),
    Field("voice", "Paste three to five comments you wrote before, or tell me to read them from your account.",
          "Replies copy your habits, never your sentences.", market=False),
    Field("language", "Which language do you write in, and which countries do you sell to?",
          "Replies and the video search use this language.", market=False),
    Field("rules", "Is there anything a reply must never say or do? Words you dislike, topics to avoid.",
          "The CEO stores this as a standing rule for every specialist.", market=False),
    Field("posting", "How do you want to post: you copy each approved reply yourself, or the app posts it through an API?",
          "Decides which credentials you need.", market=False),
)
FIELD_BY_KEY = {f.key: f for f in FIELDS}

_PLATFORM_WORDS = {
    "reddit": r"\breddit\b|\bsubreddits?\b",
    "youtube": r"\byoutube\b|\byt\b",
    "twitter": r"\bx\b|\btwitter\b|\btweets?\b",
    "hackernews": r"\bhacker ?news\b|\bhn\b",
    "github": r"\bgithub\b",
    "quora": r"\bquora\b",
    "web": r"\bforums?\b|\bblogs?\b|\bgoogle\b|\bthe web\b",
}
_PLATFORM_NAMES = {
    "reddit": "Reddit", "youtube": "YouTube", "twitter": "X", "hackernews": "Hacker News",
    "github": "GitHub", "quora": "Quora", "web": "the web",
}


def parse_platforms(text: str) -> List[str]:
    """Platforms the owner named. Empty means the owner named none we search."""
    low = (text or "").lower()
    return [p for p, pattern in _PLATFORM_WORDS.items() if re.search(pattern, low)]


def _lines(text: str) -> List[str]:
    parts = re.split(r"[\n;]+|(?<=[.!?])\s+(?=[A-Z])", text or "")
    return [p.strip(" -*\t") for p in parts if len(p.strip(" -*\t")) >= 6][:12]


def profile_from_facts(facts: Dict[str, str]) -> BusinessProfile:
    """A throwaway profile for the early search. It holds only what the owner said. The analyst builds the real one."""
    problems = _lines(facts.get("problems", "")) or _lines(facts.get("product", ""))[:2]
    site = re.search(r"https?://\S+", facts.get("site", ""))
    return BusinessProfile(
        name="",
        url=site.group(0) if site else None,
        description=facts.get("product", ""),
        main_product_or_service=facts.get("product", ""),
        icp=facts.get("target_users", ""),
        problems_solved=problems,
        pain_vocabulary=_lines(facts.get("problems", "")),
        competitors_and_alternatives=_lines(facts.get("competitors", "")),
        confirmed=False,
    )


def fingerprint(facts: Dict[str, str], platforms: List[str]) -> str:
    keys = ("product", "target_users", "problems", "competitors")
    raw = "|".join(facts.get(k, "") for k in keys) + "|" + ",".join(sorted(platforms))
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


class Intake:
    """One interview. `svc_getter` returns the service, `engine` the TeamEngine."""

    def __init__(self, svc_getter: Callable[[], Any], engine: Any):
        self._svc = svc_getter
        self.engine = engine

    # ── State ──

    @property
    def storage(self) -> Any:
        return self._svc().storage

    def state(self) -> Dict[str, Any]:
        st = self.storage.get_setting(STATE_KEY, {}) or {}
        st.setdefault("facts", {})
        st.setdefault("skipped", [])
        st.setdefault("jobs", [])
        st.setdefault("runs", 0)
        st.setdefault("fingerprint", "")
        st.setdefault("directive_id", "")
        st.setdefault("run_id", "")
        st.setdefault("memory_added", [])
        for job in st["jobs"]:
            if job.get("status") == "running" and job.get("run_id") not in _RUNNING:
                job["status"] = "interrupted"
                job["summary"] = "The server restarted before this search finished. Ask for it again."
        return st

    def _save(self, st: Dict[str, Any]) -> None:
        self.storage.set_setting(STATE_KEY, st)

    def reset(self) -> None:
        self._save({})

    # ── Answers ──

    def record(self, answers: Dict[str, Any], skip: Optional[List[str]] = None) -> Tuple[Dict[str, str], Dict[str, str]]:
        """Store the owner's answers. Returns (accepted, rejected with a reason)."""
        accepted: Dict[str, str] = {}
        rejected: Dict[str, str] = {}
        with _LOCK:
            st = self.state()
            for key, value in (answers or {}).items():
                if key not in FIELD_BY_KEY:
                    rejected[str(key)[:30]] = "Unknown question. Use: " + ", ".join(FIELD_BY_KEY)
                    continue
                text = sanitize(str(value or ""), 1500).strip()
                if len(text) < 3:
                    rejected[key] = "The answer is empty."
                    continue
                st["facts"][key] = text
                accepted[key] = text
                if key in st["skipped"]:
                    st["skipped"].remove(key)
            for key in skip or []:
                if key in FIELD_BY_KEY and not FIELD_BY_KEY[key].required and key not in st["facts"] and key not in st["skipped"]:
                    st["skipped"].append(key)
            self._save(st)
        if "rules" in accepted:
            self._store_rules(accepted["rules"])
        return accepted, rejected

    def _store_rules(self, text: str) -> None:
        """The owner's rules become standing memory. Each rule is stored once."""
        with _LOCK:
            st = self.state()
            fresh = [r for r in _lines(text) if len(r) >= 8 and r not in st["memory_added"]]
            for rule in fresh:
                self.engine.remember(rule)
                st["memory_added"].append(rule)
            self._save(st)

    # ── Questions ──

    def missing_required(self, st: Dict[str, Any]) -> List[str]:
        return [f.key for f in FIELDS if f.required and f.key not in st["facts"]]

    def next_questions(self, st: Dict[str, Any], limit: int = 2) -> List[Dict[str, str]]:
        """Ask for what blocks the search first. While a search runs, ask what the search does not need."""
        open_fields = [f for f in FIELDS if f.key not in st["facts"] and f.key not in st["skipped"]]
        searching = any(j.get("status") == "running" for j in st["jobs"])
        required = [f for f in open_fields if f.required]
        rest = [f for f in open_fields if not f.required]
        if searching or not required and st["jobs"]:
            rest.sort(key=lambda f: (f.market, FIELDS.index(f)))   # unrelated questions first
        chosen = (required + rest)[:limit]
        return [{"key": f.key, "question": f.ask, "why": f.why} for f in chosen]

    # ── Background search ──

    def platforms(self, st: Dict[str, Any]) -> List[str]:
        named = parse_platforms(st["facts"].get("platforms", ""))
        return (named or list(DEFAULT_PLATFORMS))[:5]

    def maybe_start(self, wait: bool = False) -> List[str]:
        """Start the search when the product and the target users are known and the facts changed since the last run."""
        with _LOCK:
            st = self.state()
            if self.missing_required(st) or st["runs"] >= MAX_RUNS:
                return []
            if any(j.get("status") == "running" for j in st["jobs"]):
                return []
            plats = self.platforms(st)
            fp = fingerprint(st["facts"], plats)
            if fp == st["fingerprint"]:
                return []
            run_id = f"run{int(time.time() * 1000) % 10**9}"
            st.update(fingerprint=fp, runs=st["runs"] + 1, run_id=run_id)
            st["jobs"] = [j for j in st["jobs"] if j.get("status") != "interrupted"][-12:]
            for p in plats:
                st["jobs"].append({"id": f"{run_id}:{p}", "run_id": run_id, "kind": "search", "platform": p, "status": "running", "started_at": time.time(), "summary": ""})
            self._save(st)
            facts = dict(st["facts"])
        if wait:
            self._worker(run_id, plats, facts)
        else:
            threading.Thread(target=self._worker, args=(run_id, plats, facts), daemon=True, name=f"intake-{run_id}").start()
        return [f"{run_id}:{p}" for p in plats]

    def _update_job(self, job_id: str, **changes: Any) -> None:
        with _LOCK:
            st = self.state()
            for job in st["jobs"]:
                if job["id"] == job_id:
                    job.update(changes)
            self._save(st)

    def _worker(self, run_id: str, plats: List[str], facts: Dict[str, str]) -> None:
        from agent_reach.discovery.harvester import CommunityHarvester
        from agent_reach.discovery.search_planner import SearchPlanner

        _RUNNING.add(run_id)
        try:
            svc = self._svc()
            profile = profile_from_facts(facts)
            harvester = CommunityHarvester(svc.storage)
            harvester.set_exclusions(svc._exclusions(profile))
            llm = getattr(svc, "llm", None)
            planner = SearchPlanner(llm if self.engine.llm_ready() else None)
            for plat in plats:
                job_id = f"{run_id}:{plat}"
                try:
                    queries = _spread(planner.plan_queries(profile, [plat]), QUERIES_PER_PLATFORM)
                    found: List[Any] = []
                    for q in queries:
                        for item in harvester.execute_query(q, limit=THREADS_PER_QUERY):
                            svc.storage.mark_prefetched(item.id)
                            found.append(item)
                    communities = Counter(i.community for i in found if i.community).most_common(3)
                    errors = sum(v for k, v in harvester.diagnostics.items() if k.startswith(("search_error:", "youtube_api:")))
                    if not found and errors:   # an empty result caused by failing providers is a failure, not "nothing found"
                        self._update_job(
                            job_id, status="failed", finished_at=time.time(), queries=len(queries), threads=0,
                            summary=f"No threads. {errors} search calls failed on {_PLATFORM_NAMES.get(plat, plat)}. Check the network and the search keys with reach_connections.",
                        )
                        continue
                    self._update_job(
                        job_id, status="done", finished_at=time.time(), queries=len(queries), threads=len(found),
                        communities=[{"name": n, "threads": c} for n, c in communities],
                        rejected=dict(Counter({k: v for k, v in harvester.diagnostics.items() if k.startswith("rejected:")}).most_common(4)),
                        summary=f"{len(found)} open threads from {len(queries)} searches on {_PLATFORM_NAMES.get(plat, plat)}.",
                    )
                except Exception as exc:   # one failing source must not stop the others
                    log.warning("intake search on %s failed: %s %s", plat, type(exc).__name__, str(exc)[:160])
                    self._update_job(job_id, status="failed", finished_at=time.time(), summary=f"Search on {_PLATFORM_NAMES.get(plat, plat)} failed: {type(exc).__name__}.")
        finally:
            _RUNNING.discard(run_id)

    # ── Full pipeline on the server's model ──

    def maybe_open_directive(self) -> str:
        """With a server model, start the real plan now. It builds the profile, then waits for the owner to confirm."""
        if not self.engine.llm_ready():
            return ""
        with _LOCK:
            st = self.state()
            if st["directive_id"] or self.missing_required(st):
                return str(st["directive_id"])
            facts = dict(st["facts"])
        request = suggested_request(facts)
        opened = self.engine.open_directive(request, intent="find_customers")
        did = opened.get("directive_id", "")
        if did and not opened.get("duplicate"):
            threading.Thread(target=self.engine.run, args=(did,), daemon=True, name=f"directive-{did[-6:]}").start()
        if did:
            with _LOCK:
                st = self.state()
                st["directive_id"] = did
                self._save(st)
        return did

    # ── Answer to the host ──

    def turn(
        self, answers: Optional[Dict[str, Any]] = None, skip: Optional[List[str]] = None,
        wait: bool = False, open_directive: bool = True,
    ) -> Dict[str, Any]:
        accepted, rejected = self.record(answers or {}, skip)
        started = self.maybe_start(wait=wait)
        before = self.state()["directive_id"]
        directive_id = self.maybe_open_directive() if open_directive else before
        st = self.state()
        return self.describe(st, accepted, rejected, started, directive_id, opened_now=bool(directive_id and not before))

    def describe(
        self, st: Dict[str, Any], accepted: Optional[Dict[str, str]] = None, rejected: Optional[Dict[str, str]] = None,
        started: Optional[List[str]] = None, directive_id: str = "", opened_now: bool = False,
    ) -> Dict[str, Any]:
        facts = st["facts"]
        jobs = st["jobs"]
        missing = self.missing_required(st)
        running = [j for j in jobs if j.get("status") == "running"]
        finished = [j for j in jobs if j.get("status") in ("done", "failed")]
        questions = self.next_questions(st)
        actions = _actions(accepted or {})
        say = []
        if started:
            names = [_PLATFORM_NAMES.get(j["platform"], j["platform"]) for j in jobs if j["id"] in started]
            say.append(f"I started the search on {_join(names)} in the background. It needs no answer from you. Keep answering while it runs.")
        if opened_now:
            say.append("The analyst is building your business profile on the server. I will ask you to confirm it.")
        ready = not missing and not running and bool(finished)
        out: Dict[str, Any] = {
            "collected": facts,
            "accepted": list(accepted or {}),
            "rejected": rejected or {},
            "missing_required": [{"key": k, "question": FIELD_BY_KEY[k].ask} for k in missing],
            "jobs": [{k: j.get(k) for k in ("id", "platform", "status", "summary", "threads", "communities", "queries", "rejected")} for j in jobs],
            "started_now": started or [],
            "tell_owner": " ".join(say),
            "ask_next": questions,
            "actions_for_you": actions,
            "prefetched_threads": self.storage.count_prefetched(),
            "directive_id": st["directive_id"] or None,
            "ready_for_pipeline": ready,
        }
        if ready or (not missing and not questions):
            out["suggested_request"] = suggested_request(facts)
            out["next"] = (
                "Every question is answered or skipped, and the search finished. Call ceo_open_directive with the "
                "suggested_request (unless directive_id is already set). The scout will find the threads waiting."
            )
        elif missing:
            out["next"] = "Ask the owner for the missing answers. Pass what they say to ceo_intake as answers, with the owner's own words."
        else:
            out["next"] = (
                "Ask the owner the questions in ask_next (one or two). A search is running, so do not wait for it. "
                "Pass the answers to ceo_intake as they come, and carry out actions_for_you."
            )
        return out


def _spread(queries: List[Any], n: int) -> List[Any]:
    """Pick queries across buyer stages first, so four searches do not all say the same thing."""
    chosen: List[Any] = []
    seen_stage: set = set()
    for q in queries:
        stage = getattr(q, "intent_type", "")
        if stage not in seen_stage:
            chosen.append(q)
            seen_stage.add(stage)
    for q in queries:
        if q not in chosen:
            chosen.append(q)
    return chosen[:n]


def _join(names: List[str]) -> str:
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else (names[0] if names else "")


def suggested_request(facts: Dict[str, str]) -> str:
    """The owner's words, put in order. Nothing added."""
    parts = [f"Find customers for my product. {facts.get('product', '')}".strip()]
    for key, label in (("target_users", "Target users"), ("problems", "Their problems"), ("competitors", "Alternatives they use"),
                       ("site", "Site"), ("platforms", "Where they talk")):
        if facts.get(key):
            parts.append(f"{label}: {facts[key]}")
    return "\n".join(parts)


def _actions(accepted: Dict[str, str]) -> List[str]:
    """What the host must do with an answer. The CEO stores facts. Tools change accounts, voice and settings."""
    out = []
    if "accounts" in accepted:
        out.append("Call reach_link_account once per account the owner named (platform, handle, optional alias and focus). "
                   "Then call reach_connections to tell the owner which tokens each account needs.")
    if "voice" in accepted:
        out.append("If the owner pasted comments, call reach_set_voice_samples (pass account when they belong to one account). "
                   "If the owner named an account to read, call reach_import_voice_from_account.")
    if "language" in accepted:
        out.append("Call reach_set_reply_preferences with the language the owner writes in.")
    if "posting" in accepted:
        out.append("Call reach_connections for the platforms the owner will post on, and read out the variables to set. "
                   "Change the posting mode only through reach_update_settings, and only after the owner asks.")
    if "platforms" in accepted:
        out.append("Call reach_connections for any source the owner named, so they know the keys it needs.")
    return out
