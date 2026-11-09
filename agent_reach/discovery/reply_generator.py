# -*- coding: utf-8 -*-
"""Reply drafts for a post or for one comment inside it.

Two drafts per lead. value_first helps and never names the product. product_aware
names it once with a natural first-person affiliation, at the pitch level the
settings and the account's health allow. Every draft goes through the linter
(banned words, dashes, markdown, links, affiliation, length, repeats). A failed
draft goes back to the model with the exact issues, up to `MAX_ATTEMPTS` times.
A draft that still fails is returned with `needs_human_edit=True`. A person
approves every draft before anything posts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Sequence

from agent_reach.discovery import skillpack, voice
from agent_reach.discovery.llm_client import LLMClient, LLMProviderError
from agent_reach.discovery.models import (
    BusinessProfile,
    GeneratedReply,
    LeadQualification,
    ReplyPreferences,
    ReplyTarget,
)
from agent_reach.discovery.platform_policy import can_draft, get_policy
from agent_reach.discovery.security import sanitize

log = logging.getLogger("agent_reach.discovery")

MAX_ATTEMPTS = 3
_ALLOWED_VERSIONS = ("value_first", "product_aware", "custom")
_PERSONA_HINTS = {
    "founder": r"found|started|own|run|solo|behind|builder",
    "employee": r"work|team|part of|at ",
    "maker": r"built|make|maker|wrote|builder|solo|maintain",
    "contributor": r"contribut|maintain",
}


class ReplyGenerationError(RuntimeError):
    """The platform bans drafts, or the model returned nothing usable."""


class ReplyLintError(ValueError):
    """An approved text breaks a rule. `issues` lists them."""

    def __init__(self, issues: List[str]):
        super().__init__("; ".join(issues))
        self.issues = issues


class ReplyGenerator:
    """Generates value-first and product-aware replies that pass the linter."""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = (llm_client or LLMClient()).for_tier("smart")

    # ── Public ──

    def generate_replies(
        self,
        lead: LeadQualification,
        profile: BusinessProfile,
        *,
        target: Optional[ReplyTarget] = None,
        prefs: Optional[ReplyPreferences] = None,
        max_pitch_level: Optional[int] = None,
        previous: Sequence[str] = (),
        thread_texts: Sequence[str] = (),
    ) -> GeneratedReply:
        """Draft replies for `lead`. `max_pitch_level` comes from the account's health.

        `thread_texts` holds the owner's other replies in the same thread. The prompt asks for another angle.
        """
        ctx = self.build_prompts(
            lead, profile, target=target, prefs=prefs, max_pitch_level=max_pitch_level, previous=previous,
            thread_texts=thread_texts,
        )
        prefs = ctx["prefs"]
        level, max_words, phrases = ctx["level"], ctx["max_words"], ctx["phrases"]
        base_prompt, system = ctx["prompt"], ctx["system"]
        want_product = level >= 2
        data = self._ask(base_prompt, system)
        value_first = str(data.get("value_first") or "").strip()
        product_aware = str(data.get("product_aware") or "").strip() if want_product else ""
        if not value_first or (want_product and not product_aware):
            raise ReplyGenerationError("The model did not return the requested reply versions.")

        reports: Dict[str, voice.LintReport] = {}
        for attempt in range(MAX_ATTEMPTS):
            reports["value_first"] = self._lint(value_first, "value_first", profile, prefs, min(level, 1), lead.platform, max_words, previous)
            if want_product:
                reports["product_aware"] = self._lint(
                    product_aware, "product_aware", profile, prefs, level, lead.platform, max_words, previous,
                )
            failed = {k: r for k, r in reports.items() if not r.passed}
            if not failed or attempt == MAX_ATTEMPTS - 1:
                break
            fix = self._ask(self._fix_prompt(base_prompt, value_first, product_aware, failed), system)
            if "value_first" in failed and fix.get("value_first"):
                value_first = str(fix["value_first"]).strip()
            if "product_aware" in failed and fix.get("product_aware"):
                product_aware = str(fix["product_aware"]).strip()

        needs_edit = any(not r.passed for r in reports.values())
        disclosure = self._disclosure_of(product_aware, profile.name, phrases)
        t = target or ReplyTarget()
        return GeneratedReply(
            lead_id=lead.id,
            value_first=value_first,
            product_aware=product_aware,
            selected_version="value_first",
            status="draft",
            platform=lead.platform,
            target_url=lead.url,
            affiliation_disclosure=disclosure,
            target_kind=t.target_kind,
            target_comment_id=t.target_comment_id,
            target_author=t.target_author,
            target_text=t.target_text,
            target_reason=t.reason,
            pitch_level=level,
            lint={k: r.to_dict() for k, r in reports.items()},
            needs_human_edit=needs_edit,
            generated_by="llm",
        )

    def build_prompts(
        self,
        lead: LeadQualification,
        profile: BusinessProfile,
        *,
        target: Optional[ReplyTarget] = None,
        prefs: Optional[ReplyPreferences] = None,
        max_pitch_level: Optional[int] = None,
        previous: Sequence[str] = (),
        thread_texts: Sequence[str] = (),
    ) -> Dict[str, Any]:
        """Build the exact system and user prompts the pipeline sends. The MCP server returns them to a host AI.

        Raises ReplyGenerationError when the platform bans drafted replies.
        """
        policy = get_policy(lead.platform)
        if not can_draft(lead.platform):
            raise ReplyGenerationError(f"{lead.platform}: {policy.note}")
        prefs = prefs or ReplyPreferences()
        level = prefs.pitch_level if max_pitch_level is None else min(prefs.pitch_level, max_pitch_level)
        if level >= 3 and not (prefs.allow_links and profile.url):
            level = 2
        max_words = min(prefs.max_words, policy.max_words) if policy.max_words else prefs.max_words
        phrases = self._phrases(profile.name, prefs.persona, lead.id)
        return {
            "system": skillpack.prompt("community-copywriting", "thread-engagement"),
            "prompt": self._prompt(lead, profile, target, prefs, level, max_words, phrases, previous, thread_texts),
            "level": level,
            "max_words": max_words,
            "phrases": phrases,
            "prefs": prefs,
            "want_product": level >= 2,
            "policy": {"platform": policy.name, "style": policy.style, "note": policy.note, "post": policy.post},
        }

    def check_text(
        self,
        text: str,
        *,
        kind: str,
        profile: BusinessProfile,
        prefs: Optional[ReplyPreferences] = None,
        level: Optional[int] = None,
        platform: str = "reddit",
        previous: Sequence[str] = (),
    ) -> voice.LintReport:
        """Lint any text, for example one the owner edited by hand."""
        prefs = prefs or ReplyPreferences()
        policy = get_policy(platform)
        max_words = min(prefs.max_words, policy.max_words) if policy.max_words else prefs.max_words
        return self._lint(text, kind, profile, prefs, level, platform, max_words, previous)

    def approve_reply(
        self,
        reply: GeneratedReply,
        edited_text: Optional[str] = None,
        selected_version: Optional[str] = None,
        *,
        profile: Optional[BusinessProfile] = None,
        prefs: Optional[ReplyPreferences] = None,
        previous: Sequence[str] = (),
        force: bool = False,
    ) -> GeneratedReply:
        """Mark a draft approved. With `profile`, the final text must pass the linter unless `force`."""
        version = reply.selected_version if selected_version is None else selected_version
        if version not in _ALLOWED_VERSIONS:
            raise ValueError(f"selected_version must be one of {_ALLOWED_VERSIONS}")
        edited = reply.edited_reply if edited_text is None else (edited_text.strip() or None)
        if version == "custom" and not edited:
            raise ValueError("A custom reply needs text.")
        report = None
        if profile is not None:
            text = edited or (reply.product_aware if version == "product_aware" else reply.value_first)
            report = self.check_text(
                text, kind=version, profile=profile, prefs=prefs,
                level=reply.pitch_level, platform=reply.platform, previous=previous,
            )
            if not report.passed and not force:
                raise ReplyLintError(report.issue_lines())  # the reply stays unchanged
        reply.selected_version = version  # type: ignore[assignment]
        reply.edited_reply = edited
        if report is not None:
            reply.lint["final"] = report.to_dict()
            reply.needs_human_edit = not report.passed
        reply.status = "approved"
        reply.updated_at = time.time()
        return reply

    # ── Prompt ──

    @staticmethod
    def _phrases(name: str, persona: str, seed: str) -> List[str]:
        """Pick four approved affiliation phrases that fit the persona. Stable per lead."""
        pool = skillpack.disclosure_phrases()
        hint = re.compile(_PERSONA_HINTS.get(persona, ""), re.I) if persona in _PERSONA_HINTS else None
        fitted = [p for p in pool if hint and hint.search(p)] or pool
        ordered = sorted(fitted, key=lambda p: hashlib.sha256((seed + p).encode()).hexdigest())
        return [p.replace("{product}", name or "the product") for p in ordered[:4]]

    def _prompt(
        self,
        lead: LeadQualification,
        profile: BusinessProfile,
        target: Optional[ReplyTarget],
        prefs: ReplyPreferences,
        level: int,
        max_words: int,
        phrases: List[str],
        previous: Sequence[str],
        thread_texts: Sequence[str] = (),
    ) -> str:
        policy = get_policy(lead.platform)
        t = target or ReplyTarget()
        facts = {
            "name": profile.name,
            "what_it_does": profile.main_product_or_service,
            "features": profile.features[:8],
            "outcomes": profile.customer_outcomes[:4],
            "not_for": profile.not_for[:4],
            "pricing": profile.pricing_info if profile.pricing_info and profile.pricing_info != "not stated" else "not stated",
        }
        samples = voice.pick_samples(prefs.voice_samples, 3)
        sample_block = "\n".join(f"- {sanitize(s, 600)}" for s in samples) or "none"
        shots = skillpack.few_shot(min(level, 2), limit=2)
        shot_block = "\n\n".join(
            f"Thread: {e.thread}\nGood reply: {e.good}\nWhy it works: {e.why_good}" for e in shots
        )
        user_terms = self._user_terms(prefs)
        prior = "\n".join(f"- {p[:90]}" for p in list(previous)[-5:]) or "none"
        in_thread = "\n".join(f"- {sanitize(p, 400)}" for p in list(thread_texts)[-3:])
        thread_block = (
            "\n<same_thread_replies note=\"The owner already replied in this thread. This reply answers another person on "
            "another point. Use a different opening, a different structure and different words. Do not name the product "
            "again. Do not refer to the other reply.\">\n" + in_thread + "\n</same_thread_replies>\n"
            if in_thread else ""
        )
        context_block = (
            "Background from the page (a transcript excerpt). Use only what it says. Do not describe the video "
            "beyond it, and quote no timestamp that is not listed:\n" + sanitize(t.context, 900) + "\n"
            if t.context else ""
        )
        link_line = (
            f"Link you may use once, only if the thread asks for one: {profile.url}"
            if level >= 3 and profile.url else "No links."
        )
        return f"""
<product_facts>
{json.dumps(facts, ensure_ascii=False)}
</product_facts>

<owner>
Role: {prefs.persona}
Language: {prefs.language}
Voice card:
{voice.style_card_text(prefs.voice_card)}
Voice samples (copy habits, never sentences or claims):
{sample_block}
</owner>

<settings>
platform: {lead.platform}
platform_style: {policy.style}
pitch_level: {level} (value_first uses at most level {min(level, 1)}; product_aware uses level {level})
max_words: {max_words}
min_words: {prefs.min_words}
{link_line}
Owner's own banned words: {user_terms}
</settings>

<approved_affiliation_phrases>
Pick one of these or write a close variant. Put it where it reads naturally, not at the start and not as a footer.
{chr(10).join("- " + p for p in phrases)}
</approved_affiliation_phrases>

<examples note="Quality bar only. Do not copy their wording, their opening or their structure.">
{shot_block}
</examples>

<recent_replies_do_not_reuse_wording note="Also change the opening and the ending. Do not repeat their order of ideas.">
{prior}
</recent_replies_do_not_reuse_wording>
{thread_block}
<untrusted_thread platform="{lead.platform}" community="{lead.community}">
Title: {sanitize(lead.title, 300)}
Excerpt: {sanitize(lead.excerpt, 600)}
Problem in the post: {sanitize(lead.customer_problem, 300)}
Reply target: {t.target_kind}{(" by " + t.target_author) if t.target_author else ""}
Target text: {sanitize(t.target_text or lead.excerpt, 400)}
{context_block}</untrusted_thread>

Write the replies for the reply target.
First pick the one detail in the target text that matters most (a number, a tool, a constraint) and react to it.
Use only facts from product_facts, the target text and the owner's voice samples. If you have no real detail, write less.
No greeting, no praise, no sympathy script, no not-X-but-Y frame, no lead-in line, no closing question, no sign-off, no dash of any kind.
{"product_aware must be an empty string at this pitch level." if level < 2 else "Write both versions."}
Output the JSON object only.
"""

    @staticmethod
    def _user_terms(prefs: ReplyPreferences) -> str:
        with_user = skillpack.banned_terms(True)
        without = skillpack.banned_terms(False)
        extra = (set(with_user.hard) | set(with_user.avoid)) - (set(without.hard) | set(without.avoid))
        terms = sorted(extra | {w.lower() for w in prefs.banned_words if w.strip()})
        return ", ".join(terms) if terms else "none"

    @staticmethod
    def _fix_prompt(base: str, value_first: str, product_aware: str, failed: Dict[str, voice.LintReport]) -> str:
        lines = []
        for key, report in failed.items():
            lines.append(f"{key}:")
            lines += [f"  - {line}" for line in report.issue_lines()]
        previous = {"value_first": value_first, "product_aware": product_aware}
        return (
            base
            + "\n<previous_output>\n" + json.dumps(previous, ensure_ascii=False) + "\n</previous_output>\n"
            + "<lint_issues>\n" + "\n".join(lines) + "\n</lint_issues>\n"
            + "Fix every issue by rewriting the flagged sentence in plain words. A synonym for a banned word keeps the tell, so change the sentence. "
            "Keep the rest of the text. Return the same JSON object. "
            "Fix only the versions listed, and copy the other version unchanged.\n"
        )

    def _ask(self, prompt: str, system: str) -> Dict[str, Any]:
        try:
            return self.llm.complete_json(prompt, system_prompt=system)
        except LLMProviderError as exc:
            raise ReplyGenerationError(f"The model call failed: {str(exc)[:200]}") from exc

    # ── Checks ──

    @staticmethod
    def _lint(text, kind, profile, prefs, level, platform, max_words, previous) -> voice.LintReport:
        return voice.lint_reply(
            text, kind=kind, product_name=profile.name, prefs=prefs, level=level,
            platform=platform, max_words=max_words, previous=previous,
        )

    @staticmethod
    def _disclosure_of(text: str, name: str, phrases: List[str]) -> str:
        """Return the sentence in the draft that states the affiliation, else a suggested phrase."""
        if text:
            for sent in re.split(r"(?<=[.!?])\s+", text):
                if name and name.lower() in sent.lower() and voice.has_affiliation(sent):
                    return sent.strip()
        return phrases[0] if phrases else ""
