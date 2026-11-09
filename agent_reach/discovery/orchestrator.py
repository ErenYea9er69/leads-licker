# -*- coding: utf-8 -*-
"""Discovery orchestrator: profile, plan, harvest, qualify, draft."""

from __future__ import annotations

import logging
import threading
import time
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from agent_reach.discovery import thread_comments, thread_rules, voice
from agent_reach.discovery.accounts import AccountService, account_key
from agent_reach.discovery.analytics import DiscoveryAnalytics
from agent_reach.discovery.business_engine import BusinessEngine
from agent_reach.discovery.harvester import CommunityHarvester
from agent_reach.discovery.llm_client import LLMClient
from agent_reach.discovery.models import (
    BusinessProfile,
    Campaign,
    GeneratedReply,
    LeadQualification,
    LinkedAccount,
    ReplyPreferences,
    ReplyTarget,
)
from agent_reach.discovery.platform_policy import can_draft
from agent_reach.discovery.publisher import CommunityPublisher
from agent_reach.discovery.qualifier import LeadQualifier
from agent_reach.discovery.reply_generator import ReplyGenerationError, ReplyGenerator
from agent_reach.discovery.search_planner import DEFAULT_PLATFORMS, VALID_PLATFORMS, SearchPlanner
from agent_reach.discovery.storage import DiscoveryStorage

log = logging.getLogger("agent_reach.discovery")

PER_QUERY_LIMIT = 5
REPLY_CLASSES = ("high_potential", "relevant_potential")


def validate_platforms(platforms: Optional[List[str]]) -> List[str]:
    """Lowercase, drop unknown ids, keep order. Falls back to the defaults."""
    clean = [p.lower() for p in (platforms or []) if isinstance(p, str) and p.lower() in VALID_PLATFORMS]
    return list(dict.fromkeys(clean)) or list(DEFAULT_PLATFORMS)


class DiscoveryOrchestrator:
    """Coordinates end-to-end discovery campaigns."""

    def __init__(self, storage: Optional[DiscoveryStorage] = None):
        self.storage = storage or DiscoveryStorage()
        self.active_tasks: Dict[str, threading.Event] = {}
        self._launch_lock = threading.Lock()
        self.harvester = CommunityHarvester(self.storage)
        self.accounts = AccountService(self.storage)
        self.analytics = DiscoveryAnalytics(self.storage)
        self.reload_llm()

    def reload_llm(self) -> None:
        """Rebuild every LLM-backed component. Call after settings change."""
        cfg = self.storage.get_setting("llm_settings", {}) or {}
        cfg = self._move_key_out_of_database(cfg)
        self.llm = LLMClient(
            provider=cfg.get("provider") or None,
            model=cfg.get("model") or None,
            api_key=cfg.get("api_key") or None,
        )
        self.business_engine = BusinessEngine(self.llm)
        self.qualifier = LeadQualifier(self.llm)
        self.reply_generator = ReplyGenerator(self.llm)

    def _move_key_out_of_database(self, cfg: Dict[str, Any]) -> Dict[str, Any]:
        """A model key never stays in the database. It moves to the owner-only config file."""
        key = cfg.get("api_key")
        if not key:
            return cfg
        provider = str(cfg.get("provider") or "").strip().lower()
        try:
            from agent_reach.config import Config

            if provider:
                Config().set(f"{provider}_api_key", str(key))
            clean = {k: v for k, v in cfg.items() if k != "api_key"}
            self.storage.set_setting("llm_settings", clean)
            return {**clean, "api_key": key}  # this run still uses it
        except Exception as exc:  # keep working. The key stays where it was.
            log.warning("could not move the model key to the config file: %s", str(exc)[:160])
            return cfg

    # ── Reply preferences and voice ──

    def get_prefs(self) -> ReplyPreferences:
        raw = self.storage.get_setting("reply_preferences", {}) or {}
        try:
            return ReplyPreferences.model_validate(raw)
        except Exception:
            return ReplyPreferences()

    def save_prefs(self, prefs: ReplyPreferences) -> ReplyPreferences:
        prefs.updated_at = time.time()
        self.storage.set_setting("reply_preferences", prefs.model_dump())
        return prefs

    def set_voice_samples(self, samples: List[str], append: bool = False) -> ReplyPreferences:
        """Store the owner's own comments and measure their style."""
        prefs = self.get_prefs()
        incoming = [voice.normalize_text(s) for s in samples if s and s.strip()]
        merged = (prefs.voice_samples + incoming) if append else incoming
        # Keep the newest 60 distinct samples.
        merged = list(dict.fromkeys(merged))[-60:]
        prefs.voice_samples = merged
        prefs.voice_card = voice.analyze_samples(merged) if merged else {}
        return self.save_prefs(prefs)

    def prefs_for(self, acc: Optional[LinkedAccount]) -> ReplyPreferences:
        """The owner's preferences with the account's own voice laid over them, so each account sounds like itself."""
        prefs = self.get_prefs()
        own = self.accounts.voice_of(acc)
        if own.get("voice_samples"):
            prefs.voice_samples = list(own["voice_samples"])
            prefs.voice_card = dict(own.get("voice_card") or {})
        return prefs

    def set_account_voice(self, platform: str, handle: str, samples: List[str], append: bool = False) -> Dict[str, object]:
        acc = self.accounts.get(platform, handle)
        if acc is None:
            raise KeyError(f"{platform}/{handle} is not linked. Link it first.")
        incoming = [voice.normalize_text(x) for x in samples if x and x.strip()]
        current = list(self.accounts.voice_of(acc).get("voice_samples") or [])
        merged = list(dict.fromkeys((current + incoming) if append else incoming))[-60:]
        card = voice.analyze_samples(merged) if merged else {}
        self.accounts.set_voice(acc, merged, card)
        return {"account": account_key(acc), "total_samples": len(merged), "voice_card": card}

    def import_voice_from_account(self, platform: str, handle: str, limit: int = 40) -> Dict[str, object]:
        samples = self.accounts.import_voice_samples(platform, handle, limit)
        if not samples:
            return {"imported": 0, "note": "No usable public comments found. Paste samples by hand."}
        acc = self.accounts.get(platform, handle)
        result = self.set_account_voice(platform, handle, samples, append=True)
        if len(self.accounts.list()) <= 1:   # one account: the global voice follows it, as before
            self.set_voice_samples(samples, append=True)
        return {"imported": len(samples), **result, "stored_for": account_key(acc) if acc else ""}

    def publisher_for(self, profile: Optional[BusinessProfile] = None) -> CommunityPublisher:
        profile = profile or self.storage.get_latest_business_profile()
        return CommunityPublisher(self.storage, profile=profile, prefs=self.get_prefs())

    @property
    def publisher(self) -> CommunityPublisher:
        return self.publisher_for()

    # ── Drafting ──

    def _previous_texts(self, limit: int = 20, thread: Optional[List[GeneratedReply]] = None) -> List[str]:
        """Recent replies from every account. The thread's own replies come last, so the prompt shows them."""
        out: List[str] = []
        for r in list(self.storage.list_replies(limit=limit)) + list(thread or []):
            text = r.edited_reply or (r.product_aware if r.selected_version == "product_aware" else r.value_first)
            if text and text not in out:
                out.append(text)
            if r.product_aware and r.product_aware not in out:
                out.append(r.product_aware)
        if thread:   # move the thread's texts to the end
            mine = [t for r in thread for t in (thread_rules.reply_text(r), r.product_aware) if t]
            out = [t for t in out if t not in mine] + list(dict.fromkeys(mine))
        return out

    def choose_target(
        self,
        lead: LeadQualification,
        profile: BusinessProfile,
        mode: str = "auto",
        comment_id: str = "",
        avoid: Optional[List[GeneratedReply]] = None,
    ) -> Tuple[Optional[ReplyTarget], List[ReplyTarget], List[str]]:
        """Read the thread's comments and pick where the reply goes.

        mode: "auto" takes the best scored target, "post" answers the post, "comment" needs `comment_id`
        or takes the best comment. `avoid` lists replies already on the thread: their targets and the people
        they answered are skipped. Returns (chosen, candidates, warnings).
        """
        if mode == "post":
            return None, [], []
        post, comments, warnings = thread_comments.fetch_comments(lead.url, storage=self.storage)
        if not post and not comments:
            return None, [], warnings
        ranked = thread_comments.rank_targets(post, comments, profile)
        if avoid:
            taken = {r.target_key for r in avoid}
            answered = {r.target_author.lower() for r in avoid if r.target_author}
            ranked = [
                t for t in ranked
                if ("comment:" + t.target_comment_id if t.target_kind == "comment" and t.target_comment_id else "post") not in taken
                and not (t.target_author and t.target_author.lower() in answered)
            ]
        if comment_id:
            pick = next((t for t in ranked if t.target_comment_id == comment_id), None)
            if pick is None:
                match = next((c for c in comments if str(c.get("id")) == comment_id), None)
                if match:
                    pick = ReplyTarget(
                        target_kind="comment", target_comment_id=comment_id,
                        target_author=match.get("author") or "", target_text=(match.get("body") or "")[:300],
                        reason="Chosen by the owner.",
                    )
            return pick, ranked, warnings
        if mode == "comment":
            comment_targets = [t for t in ranked if t.target_kind == "comment"]
            return (comment_targets[0] if comment_targets else None), ranked, warnings
        return (ranked[0] if ranked else None), ranked, warnings

    def draft_for_lead(
        self,
        lead: LeadQualification,
        profile: Optional[BusinessProfile] = None,
        *,
        target_mode: str = "auto",
        comment_id: str = "",
        read_thread: bool = True,
        account: str = "",
        keep_others: bool = False,
    ) -> GeneratedReply:
        """Draft replies for one lead and save them. Raises ReplyGenerationError when drafting is not allowed.

        `account` is "platform:handle". When empty, the app picks one (a thread that already has a reply keeps
        its account). `keep_others` adds a second reply on the thread instead of replacing the open draft.
        """
        profile = profile or self.storage.get_latest_business_profile()
        if profile is None:
            raise ValueError("No business profile found.")
        if not can_draft(lead.platform):
            raise ReplyGenerationError(f"{lead.platform} does not allow drafted replies. Use the thread for research.")
        settings = self.storage.get_posting_settings()
        siblings = self.storage.thread_replies(lead.url)
        acc: Optional[LinkedAccount] = None
        if account:
            acc = self.accounts.get_by_key(account)
            if acc is None:
                raise ReplyGenerationError(f"{account} is not linked. Link it first.")
        else:
            acc, why = self.accounts.pick(
                lead.platform, thread=siblings, community=lead.community, settings=settings, product_name=profile.name
            )
            if acc is None and self.accounts.for_platform(lead.platform):
                raise ReplyGenerationError(why)
        key = account_key(acc) if acc else ""
        prefs = self.prefs_for(acc)
        health = self.accounts.health(lead.platform, acc.handle if acc else None, product_name=profile.name)
        max_level = health.max_pitch_level if health.known else None

        # Open drafts do not block a new draft unless the owner keeps them. Replies already approved or sent do.
        avoid = [r for r in siblings if r.status != "draft" or keep_others]
        target = None
        if read_thread or comment_id or avoid:
            target, _, _ = self.choose_target(lead, profile, target_mode, comment_id, avoid=avoid)
        probe = GeneratedReply(
            lead_id=lead.id, value_first="x", platform=lead.platform, account_id=key,
            target_kind=target.target_kind if target else "post",
            target_comment_id=target.target_comment_id if target else "",
            target_author=target.target_author if target else "",
        )
        code, message = thread_rules.check_draft(siblings, probe, settings, texts=[], keep_others=keep_others)
        if code != "ok":
            raise ReplyGenerationError(f"{code}: {message}")

        others = [r for r in siblings if r.id not in thread_rules.replaced_by(siblings, probe, keep_others)]
        reply = self.reply_generator.generate_replies(
            lead, profile, target=target, prefs=prefs, max_pitch_level=max_level,
            previous=self._previous_texts(thread=others),
            thread_texts=[thread_rules.reply_text(r) for r in others if r.status != "rejected"],
        )
        reply.account_id = key
        code, message = thread_rules.check_draft(siblings, reply, settings, keep_others=keep_others)
        if code != "ok":
            raise ReplyGenerationError(f"{code}: {message}")
        self.storage.save_reply(reply, keep_others=keep_others)
        return reply

    def approve_reply(
        self, reply_id: str, edited_text: Optional[str] = None, selected_version: Optional[str] = None,
        force: bool = False,
    ) -> GeneratedReply:
        reply = self.storage.get_reply(reply_id)
        if reply is None:
            raise KeyError(f"No reply {reply_id}.")
        profile = self.storage.get_latest_business_profile()
        previous = [t for t in self._previous_texts() if t not in (reply.value_first, reply.product_aware)]
        self.reply_generator.approve_reply(
            reply, edited_text, selected_version, profile=profile, prefs=self.get_prefs(),
            previous=previous, force=force,
        )
        self.storage.save_reply(reply)
        return reply

    # ── Campaign ──

    @staticmethod
    def _exclusions(profile: BusinessProfile) -> List[str]:
        """Hosts to skip: the user's own site. Competitor sites are guessed from their names."""
        hosts = []
        if profile.url:
            host = (urlsplit(profile.url).hostname or "").lower()
            hosts.append(host[4:] if host.startswith("www.") else host)
        return [h for h in hosts if h]

    def run_campaign_sync(
        self,
        campaign_name: str = "Lead Discovery",
        platforms: Optional[List[str]] = None,
        max_leads: int = 15,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        campaign_id: Optional[str] = None,
        communities: Optional[List[str]] = None,
    ) -> Campaign:
        profile = self.storage.get_latest_business_profile()
        if not profile:
            raise ValueError("No business profile found. Analyze a website or product description first.")
        chosen = validate_platforms(platforms)

        campaign = self.storage.get_campaign(campaign_id) if campaign_id else None
        if campaign is None:
            campaign = Campaign(
                name=campaign_name, business_profile_id=profile.id, status="running",
                selected_platforms=chosen, current_step="Planning queries...", progress_percentage=10,
            )
            self.storage.save_campaign(campaign)
        cancel_event = self.active_tasks.get(campaign.id)

        def cancelled() -> bool:
            return bool(cancel_event and cancel_event.is_set())

        def note(step: str, pct: int) -> None:
            campaign.current_step, campaign.progress_percentage = step, pct
            self.storage.save_campaign(campaign)
            if progress_callback:
                progress_callback(step, pct)

        note("Planning search queries", 15)
        queries = SearchPlanner(self.llm).plan_queries(profile, chosen, communities)
        campaign.queries = queries
        note(f"Planned {len(queries)} queries. Searching...", 30)

        self.harvester.diagnostics = Counter()
        self.harvester.set_exclusions(self._exclusions(profile))
        self.qualifier.reset_budget()

        found = qualified = high = 0
        rejections: Counter = Counter()
        step = 55 / max(1, len(queries))
        progress = 30.0

        for q in queries:
            if cancelled():
                campaign.status = "cancelled"
                note("Cancelled by the operator.", int(progress))
                return campaign
            items = self.harvester.execute_query(q, limit=PER_QUERY_LIMIT)
            found += len(items)

            for item in items:
                if cancelled():
                    break
                lead = self.qualifier.qualify(item, profile)
                if lead is None:
                    rejections[f"qualifier:{self.qualifier.last_rejection}"] += 1
                    continue
                self.storage.save_lead(lead, campaign_id=campaign.id)
                qualified += 1
                high += lead.classification == "high_potential"
                if lead.classification in REPLY_CLASSES:
                    if lead.reply_policy != "draft":
                        rejections["reply_human_only"] += 1
                    elif not self.llm.is_configured:
                        rejections["reply_skipped_no_model"] += 1
                    else:
                        try:
                            # Reading comments costs a request, so only the best leads get it.
                            self.draft_for_lead(lead, profile, read_thread=lead.classification == "high_potential")
                        except Exception as exc:  # a failed draft must not lose the lead
                            log.warning("reply draft failed for %s: %s", lead.id, str(exc)[:200])
                            rejections["reply_draft_failed"] += 1
                if qualified >= max_leads:
                    break

            progress += step
            campaign.progress_percentage = min(90, int(progress))
            campaign.total_found, campaign.total_qualified = found, qualified
            campaign.high_potential_count = high
            campaign.current_step = f"Searched {q.platform}: {q.query[:40]}"
            campaign.diagnostics = dict(self.harvester.diagnostics + rejections)
            self.storage.save_campaign(campaign)
            if qualified >= max_leads:
                break

        campaign.status = "completed"
        campaign.completed_at = time.time()
        campaign.diagnostics = dict(self.harvester.diagnostics + rejections)
        note(f"Finished. {found} open threads checked, {qualified} qualified leads.", 100)
        return campaign

    def cancel_campaign(self, campaign_id: str) -> bool:
        event = self.active_tasks.get(campaign_id)
        if not event:
            return False
        event.set()
        return True

    def run_campaign_background(
        self,
        campaign_name: str = "Lead Discovery",
        platforms: Optional[List[str]] = None,
        max_leads: int = 15,
        communities: Optional[List[str]] = None,
    ) -> str:
        profile = self.storage.get_latest_business_profile()
        if not profile:
            raise ValueError("No business profile found. Analyze a website or product description first.")
        chosen = validate_platforms(platforms)
        with self._launch_lock:
            if self.active_tasks:
                raise RuntimeError("A campaign is already running. Cancel it or wait for it to finish.")
            campaign = Campaign(
                name=campaign_name, business_profile_id=profile.id, status="running",
                selected_platforms=chosen, current_step="Starting...", progress_percentage=5,
            )
            self.storage.save_campaign(campaign)
            self.active_tasks[campaign.id] = threading.Event()

        def _worker() -> None:
            try:
                self.run_campaign_sync(campaign_name, chosen, max_leads, campaign_id=campaign.id, communities=communities)
            except Exception as exc:
                log.exception("campaign %s failed", campaign.id)
                latest = self.storage.get_campaign(campaign.id) or campaign
                latest.status = "failed"
                latest.current_step = f"Failed: {type(exc).__name__}: {str(exc)[:200]}"
                self.storage.save_campaign(latest)
            finally:
                self.active_tasks.pop(campaign.id, None)

        threading.Thread(target=_worker, daemon=True).start()
        return campaign.id
