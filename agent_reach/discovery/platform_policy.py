# -*- coding: utf-8 -*-
"""Per-platform reply policy. Mirrors skills/platform-safety.

draft:  "allowed" means the app may write a draft. "none" means it must not.
post:   "manual" means a person posts. "api" means the app may post when the
        owner supplies credentials and every gate passes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class PlatformPolicy:
    name: str
    draft: str
    post: str
    max_words: int
    style: str
    note: str


POLICIES: Dict[str, PlatformPolicy] = {
    "reddit": PlatformPolicy(
        "reddit", "allowed", "api", 150,
        "Plain paragraphs. No links. No emoji unless the voice samples use them. Match the thread's tone.",
        "Many communities ban AI-written content. The owner rewrites and posts every reply.",
    ),
    "hackernews": PlatformPolicy(
        "hackernews", "none", "manual", 0,
        "No draft.",
        "Hacker News bans generated and AI-edited comments (March 2026). Use these threads for research.",
    ),
    "github": PlatformPolicy(
        "github", "allowed", "api", 120,
        "Short and practical. Name the version, the error or the command. Stay on the issue's topic. State the affiliation early.",
        "Comment only when the reply helps the issue.",
    ),
    "quora": PlatformPolicy(
        "quora", "allowed", "manual", 150,
        "Plain paragraphs. A little longer is fine, but open with the answer. State the affiliation in the answer.",
        "Manual posting only.",
    ),
    "twitter": PlatformPolicy(
        "twitter", "allowed", "manual", 45,
        "One or two short sentences. No hashtags, no emoji unless the owner uses them, no thread numbering. Match the owner's timeline voice.",
        "X forbids unsolicited automated replies. A person sends every reply.",
    ),
    "youtube": PlatformPolicy(
        "youtube", "allowed", "manual", 70,
        "One short comment. Open with a detail from the video or from the comment you answer. No links, no emoji unless "
        "the owner uses them, no 'great video', no timestamps the transcript does not show.",
        "The app never posts to YouTube. The owner pastes the comment from the channel's own account.",
    ),
    "web": PlatformPolicy(
        "web", "allowed", "manual", 150,
        "Plain paragraphs. Follow the forum's rules.",
        "Manual posting only.",
    ),
}


def get_policy(platform: str) -> PlatformPolicy:
    return POLICIES.get((platform or "").lower(), POLICIES["web"])


def can_draft(platform: str) -> bool:
    return get_policy(platform).draft == "allowed"


def can_auto_post(platform: str) -> bool:
    return get_policy(platform).post == "api"
