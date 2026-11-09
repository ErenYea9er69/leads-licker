# -*- coding: utf-8 -*-
"""Publishing with hard safety gates.

Gate order, first failure wins:
  1. emergency stop
  2. draft mode
  3. human approval
  4. platform policy (Hacker News never, X and Quora manual only)
  5. content lint (banned words, dashes, markdown, links, affiliation, length)
  6. community rules the owner recorded (self promotion, AI content, links, karma)
  7. optional community whitelist
  8. thread rules (one account per thread, a target takes one reply, at most two or three replies,
     different openings, one product mention, a gap between replies; see thread_rules.py)
  9. account health (pitch level allowed by age and karma)
  10. product mention ratio (at most one product reply in ten, counted per account)
  11. daily cap (the lower of the owner's cap and the account's cap, counted per account)
  12. gap between posts on the platform, with jitter, across all the owner's accounts
  13. thread still open (Reddit and GitHub, live check)

Manual mode never calls a platform API. It returns text and a direct link, and
the reply counts as published only after the person confirms. Automatic mode
needs two keys: the posting mode "automatic" and AGENT_REACH_ALLOW_AUTOPOST=1,
plus approved API credentials in the environment. Credentials are never stored.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests

from agent_reach.discovery import thread_rules, voice
from agent_reach.discovery.accounts import AccountService, account_key
from agent_reach.discovery.models import (
    BusinessProfile,
    GeneratedReply,
    LeadQualification,
    PostingSettings,
    ReplyPreferences,
)
from agent_reach.discovery.platform_policy import can_auto_post, can_draft, get_policy
from agent_reach.discovery.storage import DiscoveryStorage
from agent_reach.discovery.thread_check import (
    RedditMeta,
    judge_reddit,
    reddit_post_id,
    youtube_video_id,
)

_GITHUB_ISSUE = re.compile(r"github\.com/([^/]+)/([^/]+)/issues/(\d+)")


def _short(err: object) -> str:
    return str(err)[:200]


class CommunityPublisher:
    """Applies every gate, then posts through an approved API or hands the text to the owner."""

    def __init__(
        self,
        storage: Optional[DiscoveryStorage] = None,
        session: Optional[requests.Session] = None,
        profile: Optional[BusinessProfile] = None,
        prefs: Optional[ReplyPreferences] = None,
    ):
        self.storage = storage or DiscoveryStorage()
        self.session = session or requests.Session()
        self.profile = profile
        self.prefs = prefs

    def _accounts(self) -> AccountService:
        return AccountService(self.storage, self.session)

    def resolve_account(self, reply: GeneratedReply, lead: LeadQualification):
        """Return (account, error_code, message). The reply's own account wins. A single linked account is the default."""
        svc = self._accounts()
        if reply.account_id:
            acc = svc.get_by_key(reply.account_id)
            if acc is None:
                return None, "account_missing", f"{reply.account_id} is not linked any more. Link it again or choose another account."
            return acc, "", ""
        linked = svc.for_platform(lead.platform)
        if len(linked) > 1:
            return None, "account_needed", (
                f"{len(linked)} {lead.platform} accounts are linked. Save the reply with an account, "
                "or let the app pick one, before publishing."
            )
        return (linked[0] if linked else None), "", ""

    # ── Gates ──

    def gate(
        self, reply: GeneratedReply, lead: LeadQualification, settings: PostingSettings
    ) -> Tuple[str, str]:
        """Return (code, message). The code is "ok" when every gate passes."""
        if settings.emergency_stop:
            return "emergency_stop", "Emergency stop is active. All publishing is halted."
        if settings.mode == "draft":
            return "draft_mode", "Draft mode is on. Publishing is disabled."
        if reply.status not in ("approved", "pending_manual_post"):
            return "not_approved", "Approve the reply before publishing."
        text = self._get_reply_content(reply).strip()
        if not text:
            return "empty", "The reply is empty."

        policy = get_policy(lead.platform)
        if not can_draft(lead.platform):
            return "platform_policy", policy.note

        kind = self._kind_of(reply, text)
        level = reply.pitch_level if kind == "product_aware" else 0

        report = voice.lint_reply(
            text, kind=kind, product_name=self.profile.name if self.profile else "",
            prefs=self.prefs, level=level, platform=lead.platform,
            max_words=policy.max_words or None,
        )
        if not report.passed:
            return "lint", "The text breaks writing rules: " + "; ".join(report.issue_lines())

        rule = self.storage.get_community_rule(lead.community) if lead.community else None
        if lead.platform == "reddit" and lead.community:
            if rule is None and settings.require_rules_ack:
                return "rules_not_read", (
                    f"Read the rules of {lead.community}, then record them with the rules tool before posting."
                )
            if rule is not None:
                if not rule.ai_content_allowed:
                    return "rules_no_ai", f"{lead.community} bans AI-written content. Write this one yourself."
                if kind == "product_aware" and rule.self_promo in ("banned", "thread_only"):
                    return "rules_no_promo", f"{lead.community} does not allow self promotion here ({rule.self_promo})."
                if re.search(r"https?://|\b\w+\.(?:com|io|ai|app|co|dev|net)\b", text, re.I) and not rule.links_allowed:
                    return "rules_no_links", f"{lead.community} does not allow links in comments."

        if settings.allowed_communities and lead.community:
            allowed = {c.lower().removeprefix("r/") for c in settings.allowed_communities}
            if lead.community.lower().removeprefix("r/") not in allowed:
                return "not_whitelisted", f"{lead.community} is not in the allowed communities."

        code, message = thread_rules.check_publish(
            self.storage.thread_replies(lead.url), reply, kind, text, settings,
            product_name=self.profile.name if self.profile else "",
        )
        if code != "ok":
            return code, message

        account, err_code, err_msg = self.resolve_account(reply, lead)
        if err_code:
            return err_code, err_msg
        own_key = account_key(account) if account is not None and reply.account_id else None
        health = None
        if account is not None or settings.require_account_health:
            health = self._accounts().health(
                lead.platform, account.handle if account else None, self.profile.name if self.profile else ""
            )
        if kind == "product_aware" and health is not None:
            if not health.known and settings.require_account_health:
                return "account_unknown", (
                    f"Link your {lead.platform} account and refresh it so the app can read its age and karma."
                )
            if level > health.max_pitch_level:
                return "account_health", (
                    f"Your account is at stage '{health.stage_name}' and allows pitch level {health.max_pitch_level}. "
                    f"This reply uses level {level}. Post helpful replies first or use the value-first version."
                )
            if rule is not None and rule.min_karma and account and account.snapshot:
                karma = account.snapshot.get("comment_karma") or 0
                if karma < rule.min_karma:
                    return "rules_min_karma", f"{lead.community} wants {rule.min_karma} karma. The account has {karma}."

        if kind == "product_aware" and settings.max_mention_ratio < 1:
            blocked = self._mention_gate(lead.platform, settings, account.snapshot if account else {}, own_key)
            if blocked:
                return "mention_ratio", blocked

        if kind == "product_aware" and settings.product_community_gap_days:
            others = [a for a in self.storage.product_posters(lead.platform, lead.community, settings.product_community_gap_days) if a != (own_key or "")]
            if others:
                return "community_overlap", (
                    f"{others[0] or 'Another account of yours'} named the product in {lead.community} in the last "
                    f"{settings.product_community_gap_days} days. Two of your accounts naming it in one community looks coordinated. "
                    "Use the value-first version here, or wait."
                )

        cap = settings.daily_limit
        if health is not None and health.known:
            cap = min(cap, health.suggested_daily_cap)
        if self.storage.count_posts_today(lead.platform, own_key) >= cap:
            who = f"{own_key}" if own_key else lead.platform
            return "daily_cap", f"Daily limit of {cap} reached for {who}."

        last = self.storage.last_published_at(lead.platform)
        if last and settings.min_interval_seconds > 0:
            need = self._interval(settings, last)
            wait = int(need - (time.time() - last))
            if wait > 0:
                return "interval", f"Wait {wait} more seconds between posts on {lead.platform}."
        return "ok", "Ready to publish."

    def can_publish(
        self, reply: GeneratedReply, lead: LeadQualification, settings: PostingSettings
    ) -> Tuple[bool, str]:
        code, message = self.gate(reply, lead, settings)
        return code == "ok", message

    def _mention_gate(
        self, platform: str, settings: PostingSettings, snapshot: Dict[str, Any], account_id: Optional[str] = None
    ) -> str:
        """At most `max_mention_ratio` of recent comments may name the product, this one included."""
        kinds = self.storage.recent_published_kinds(platform, limit=30, account_id=account_id)
        app_total, app_pa = len(kinds), sum(1 for k in kinds if k == "product_aware")
        snap_total = int(snapshot.get("recent_comment_count") or 0)
        snap_pa = round((snapshot.get("recent_mention_ratio") or 0) * snap_total)
        total = max(app_total, snap_total) + 1
        pa = max(app_pa, snap_pa) + 1
        if pa / total > settings.max_mention_ratio:
            need = int(pa / settings.max_mention_ratio) - total + 1
            hint = (
                "Refresh your linked account so the app can count your earlier comments, or "
                if not snap_total else ""
            )
            return (
                f"{pa} of the last {total} comments would name the product. "
                f"{hint}post about {max(1, need)} more helpful replies without the product first."
            )
        return ""

    @staticmethod
    def _interval(settings: PostingSettings, last_published: float) -> float:
        """Minimum gap plus a jitter that stays fixed for one previous post."""
        digest = hashlib.sha256(f"{last_published:.0f}".encode()).digest()
        fraction = int.from_bytes(digest[:2], "big") / 65535.0
        return settings.min_interval_seconds * (1.0 + settings.interval_jitter * fraction)

    # ── Publish ──

    def publish_or_copy(
        self, reply: GeneratedReply, lead: LeadQualification, settings: PostingSettings
    ) -> Dict[str, Any]:
        code, reason = self.gate(reply, lead, settings)
        kind = self._kind_of(reply, self._get_reply_content(reply))
        if code != "ok":
            self.storage.log_post(
                lead.id, reply.id, lead.platform, lead.url, "", settings.mode, "rejected", reason, kind=kind,
                account_id=reply.account_id,
            )
            return {"success": False, "reason": reason, "code": code}
        account, _, _ = self.resolve_account(reply, lead)

        content = self._final_content(reply)
        note = ""
        if settings.mode == "automatic":
            if os.getenv("AGENT_REACH_ALLOW_AUTOPOST") != "1":
                note = "Automatic posting needs AGENT_REACH_ALLOW_AUTOPOST=1 in the environment. Falling back to manual."
            elif not can_auto_post(lead.platform):
                note = f"{lead.platform} has no approved posting API in this app. Falling back to manual."
            elif lead.platform == "reddit" and self._reddit_creds(settings, account):
                return self._publish_reddit_api(reply, lead, content, settings, kind, account)
            elif lead.platform == "github" and self._github_token(settings, account):
                return self._publish_github_api(reply, lead, content, settings, kind, account)
            else:
                note = "No API credentials in the environment. Falling back to manual."

        reply.status = "pending_manual_post"
        self.storage.save_reply(reply)
        self.storage.log_post(
            lead.id, reply.id, lead.platform, lead.url, content, settings.mode, "pending_manual_post", kind=kind,
            account_id=reply.account_id,
        )
        return {
            "success": True,
            "action": "copy_and_open",
            "message": (
                f"Copy the reply, post it from {reply.account_id.split(':', 1)[1]}, then confirm."
                if reply.account_id else "Copy the reply, post it from your own account, then confirm."
            ),
            "account": reply.account_id,
            "note": note,
            "target_url": self._target_link(reply, lead),
            "text": content,
            "kind": kind,
        }

    def confirm_manual_post(
        self, reply: GeneratedReply, lead: LeadQualification, comment_url: str = ""
    ) -> Dict[str, Any]:
        """The person says they posted the reply. Only now does it count as published."""
        if reply.status != "pending_manual_post":
            raise ValueError("Only a reply waiting for manual posting can be confirmed.")
        reply.status = "published"
        reply.published_at = time.time()
        if comment_url:
            reply.published_url = comment_url
        self.storage.save_reply(reply)
        content = self._final_content(reply)
        self.storage.log_post(
            lead.id, reply.id, lead.platform, lead.url, content,
            "manual", "published", "Confirmed by the user", kind=self._kind_of(reply, content),
            account_id=reply.account_id,
        )
        return {"success": True, "reply": reply.model_dump()}

    # ── Content ──

    @staticmethod
    def _get_reply_content(reply: GeneratedReply) -> str:
        if reply.selected_version == "custom" or reply.edited_reply:
            return reply.edited_reply or ""
        if reply.selected_version == "product_aware":
            return reply.product_aware
        return reply.value_first

    def _kind_of(self, reply: GeneratedReply, text: str) -> str:
        if reply.selected_version in ("value_first", "product_aware") and not reply.edited_reply:
            return reply.selected_version
        name = self.profile.name if self.profile else ""
        return "product_aware" if name and voice.count_product_mentions(text, name) else "value_first"

    def _final_content(self, reply: GeneratedReply) -> str:
        """The text goes out as approved. The affiliation sits inside it, written by the owner or the model."""
        return self._get_reply_content(reply).strip()

    @staticmethod
    def _target_link(reply: GeneratedReply, lead: LeadQualification) -> str:
        """A direct link to the comment when the reply answers one, else the thread."""
        if lead.platform == "reddit" and reply.target_kind == "comment" and reply.target_comment_id:
            pid = reddit_post_id(lead.url)
            if pid:
                return f"https://www.reddit.com/comments/{pid}/_/{reply.target_comment_id}/"
        if lead.platform == "youtube":
            from agent_reach.discovery import youtube

            vid = youtube_video_id(lead.url)
            if vid:
                return youtube.comment_link(vid, reply.target_comment_id if reply.target_kind == "comment" else "")
        return lead.url

    # ── Reddit ──

    def _reddit_creds(self, settings: PostingSettings, account=None) -> Optional[Dict[str, str]]:
        """Credentials for one linked account, else the single set in the environment."""
        if account is not None:
            return self._accounts().credentials(account)
        creds = {
            "client_id": settings.reddit_client_id or os.getenv("REDDIT_CLIENT_ID") or "",
            "client_secret": settings.reddit_client_secret or os.getenv("REDDIT_CLIENT_SECRET") or "",
            "username": settings.reddit_username or os.getenv("REDDIT_USERNAME") or "",
            "password": settings.reddit_password or os.getenv("REDDIT_PASSWORD") or "",
        }
        return creds if all(creds.values()) else None

    def _github_token(self, settings: PostingSettings, account=None) -> Optional[str]:
        if account is not None:
            creds = self._accounts().credentials(account)
            return creds["token"] if creds else None
        return settings.github_token or os.getenv("GITHUB_TOKEN") or None

    def _fail(self, lead, reply, content, settings, reason: str, kind: str = "") -> Dict[str, Any]:
        self.storage.log_post(
            lead.id, reply.id, lead.platform, lead.url, content, settings.mode, "failed", reason, kind=kind,
            account_id=reply.account_id,
        )
        return {"success": False, "reason": reason, "code": "api_failed", "fallback_action": "copy_and_open"}

    def _publish_reddit_api(self, reply, lead, content, settings, kind: str, account=None) -> Dict[str, Any]:
        creds = self._reddit_creds(settings, account)
        pid = reddit_post_id(lead.url)
        if not creds or not pid:
            return self._fail(lead, reply, content, settings, "Missing Reddit credentials or post id.", kind)
        ua = f"script:agent-reach-lead:2.2 (by /u/{creds['username']})"
        parent = (
            f"t1_{reply.target_comment_id}"
            if reply.target_kind == "comment" and reply.target_comment_id else f"t3_{pid}"
        )
        try:
            token_resp = self.session.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(creds["client_id"], creds["client_secret"]),
                data={"grant_type": "password", "username": creds["username"], "password": creds["password"]},
                headers={"User-Agent": ua},
                timeout=10,
            )
            token = token_resp.json().get("access_token") if token_resp.status_code == 200 else None
            if not token:
                return self._fail(lead, reply, content, settings, "Reddit login failed.", kind)

            meta = RedditMeta(creds["client_id"], creds["client_secret"], session=self.session).fetch([pid])
            health = judge_reddit(meta.get(pid))
            if health.reject in ("archived", "locked", "removed"):
                return self._fail(lead, reply, content, settings, f"Thread is {health.reject}.", kind)

            resp = self.session.post(
                "https://oauth.reddit.com/api/comment",
                headers={"Authorization": f"Bearer {token}", "User-Agent": ua},
                data={"api_type": "json", "thing_id": parent, "text": content},
                timeout=10,
            )
            body = resp.json() if resp.status_code == 200 else {}
            errors = (body.get("json") or {}).get("errors") or []
            if resp.status_code != 200 or errors:
                return self._fail(lead, reply, content, settings, f"Reddit refused the comment: {_short(errors or resp.status_code)}", kind)
            things = ((body.get("json") or {}).get("data") or {}).get("things") or []
            data = (things[0].get("data") if things else None) or {}
            reply.published_comment_id = str(data.get("id") or "")
            if data.get("permalink"):
                reply.published_url = "https://www.reddit.com" + data["permalink"]
        except (requests.RequestException, ValueError) as exc:
            return self._fail(lead, reply, content, settings, f"Reddit request failed: {type(exc).__name__}", kind)

        return self._mark_published(reply, lead, content, settings, "Published through the Reddit API.", kind)

    # ── GitHub ──

    def _publish_github_api(self, reply, lead, content, settings, kind: str, account=None) -> Dict[str, Any]:
        m = _GITHUB_ISSUE.search(lead.url)
        if not m:
            return self._fail(lead, reply, content, settings, "Not a GitHub issue URL.", kind)
        owner, repo, number = m.groups()
        token = self._github_token(settings, account)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "agent-reach-lead/2.2",
        }
        base = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"
        try:
            issue = self.session.get(base, headers=headers, timeout=10)
            if issue.status_code == 200 and (issue.json().get("locked") or issue.json().get("state") != "open"):
                return self._fail(lead, reply, content, settings, "Issue is closed or locked.", kind)
            resp = self.session.post(f"{base}/comments", headers=headers, json={"body": content}, timeout=10)
            if resp.status_code not in (200, 201):
                return self._fail(lead, reply, content, settings, f"GitHub returned {resp.status_code}.", kind)
            created = resp.json()
            reply.published_comment_id = str(created.get("id") or "")
            reply.published_url = created.get("html_url") or ""
        except (requests.RequestException, ValueError) as exc:
            return self._fail(lead, reply, content, settings, f"GitHub request failed: {type(exc).__name__}", kind)
        return self._mark_published(reply, lead, content, settings, "Published through the GitHub API.", kind)

    def _mark_published(self, reply, lead, content, settings, message: str, kind: str) -> Dict[str, Any]:
        reply.status = "published"
        reply.published_at = time.time()
        self.storage.save_reply(reply)
        self.storage.log_post(
            lead.id, reply.id, lead.platform, lead.url, content, settings.mode, "published", kind=kind,
            account_id=reply.account_id,
        )
        return {"success": True, "message": message, "url": reply.published_url}
