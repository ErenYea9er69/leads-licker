# -*- coding: utf-8 -*-
"""Rules for replying more than once in one thread.

The owner may run several accounts. Several accounts that talk in one thread look like several
independent people, and the platforms treat that as manipulation. So the rules are strict:

  1. A target (the post, or one comment) takes one reply, ever. No second account and no second draft.
  2. One account per thread. The first reply fixes the account. Other accounts stay out of the thread.
  3. At most `max_replies_per_thread` replies in a thread (default 2, never more than 3).
  4. A second reply goes to a different comment, and not to an author the owner already answered.
  5. Replies in one thread open differently and differ in wording.
  6. Only one reply per thread names the product.
  7. A gap of `min_thread_gap_minutes` separates two replies in one thread.

Rules 1 to 5 run when a draft is saved. Rules 1 to 7 run again at the publish gate.
"""

from __future__ import annotations

import re
import time
from typing import List, Optional, Tuple

from agent_reach.discovery import voice
from agent_reach.discovery.models import GeneratedReply, PostingSettings

_WORD = re.compile(r"[a-z0-9']+")


def reply_text(reply: GeneratedReply) -> str:
    """The text that goes out: the edit, else the chosen version."""
    if reply.edited_reply:
        return reply.edited_reply
    return reply.product_aware if reply.selected_version == "product_aware" else reply.value_first


def opening(text: str, words: int = 3) -> str:
    return " ".join(_WORD.findall((text or "").lower())[:words])


def replaced_by(siblings: List[GeneratedReply], reply: GeneratedReply, keep_others: bool = False) -> List[str]:
    """Ids of the replies that saving `reply` overwrites. They never count against the new draft.

    Same lead and same target: an unsent reply (draft or approved) is overwritten. Same lead, other target:
    the open draft is overwritten, unless the caller keeps other drafts.
    """
    own = [r for r in siblings if r.lead_id == reply.lead_id and r.id != reply.id]
    same = [r for r in own if r.target_key == reply.target_key and r.status in ("draft", "approved")]
    if same:
        return [r.id for r in same]
    if keep_others or any(r.target_key == reply.target_key for r in own):
        return []
    drafts = sorted((r for r in own if r.status == "draft"), key=lambda r: r.updated_at, reverse=True)
    return [drafts[0].id] if drafts else []


def _live(siblings: List[GeneratedReply], reply: GeneratedReply, keep_others: bool = False) -> List[GeneratedReply]:
    gone = set(replaced_by(siblings, reply, keep_others))
    return [r for r in siblings if r.id != reply.id and r.id not in gone and r.status != "rejected"]


def _core(
    others: List[GeneratedReply], reply: GeneratedReply, settings: PostingSettings, mine: List[str]
) -> Tuple[str, str]:
    """Rules 1 to 5 against the replies that count."""
    if not others:
        return "ok", ""
    if any(r.target_key == reply.target_key for r in others):
        return "target_taken", (
            "This target already has a reply in the app. A post or a comment takes one reply. "
            "Reject the earlier reply first, or choose another comment."
        )
    if reply.account_id:
        owners = {r.account_id for r in others if r.account_id}
        if owners and reply.account_id not in owners:
            owner = sorted(owners)[0]
            return "thread_account", (
                f"{owner} already replied in this thread. One account per thread, so use {owner} here "
                "and keep the other accounts out of it."
            )
    cap = max(1, min(settings.max_replies_per_thread, 3))
    if len(others) >= cap:
        return "thread_cap", f"This thread already has {len(others)} replies. The limit is {cap}."
    if reply.target_author:
        wanted = reply.target_author.lower()
        if any(r.target_author and r.target_author.lower() == wanted for r in others):
            return "same_author", f"A reply to {reply.target_author} already exists in this thread. Answer another person."
    heads = {opening(t) for r in others for t in (reply_text(r), r.value_first, r.product_aware) if t}
    if any(t and opening(t) in heads for t in mine):
        return "same_opening", "Another reply in this thread opens with the same words. Open differently."
    return "ok", ""


def check_draft(
    siblings: List[GeneratedReply],
    reply: GeneratedReply,
    settings: PostingSettings,
    texts: Optional[List[str]] = None,
    keep_others: bool = False,
) -> Tuple[str, str]:
    """Rules 1 to 5 for a draft. `siblings` holds every reply already on the thread. Returns (code, message)."""
    mine = texts if texts is not None else [t for t in (reply.value_first, reply.product_aware) if t]
    return _core(_live(siblings, reply, keep_others), reply, settings, mine)


def check_publish(
    siblings: List[GeneratedReply],
    reply: GeneratedReply,
    kind: str,
    text: str,
    settings: PostingSettings,
    product_name: str = "",
    now: Optional[float] = None,
) -> Tuple[str, str]:
    """Rules 1 to 7 for a reply about to go out. Only replies approved, handed over or posted count here."""
    sent = [r for r in siblings if r.id != reply.id and r.status in ("approved", "pending_manual_post", "published")]
    code, message = _core(sent, reply, settings, [text])
    if code != "ok":
        return code, message
    if kind == "product_aware":
        for r in sent:
            body = reply_text(r)
            if r.selected_version == "product_aware" or (product_name and voice.count_product_mentions(body, product_name)):
                return "thread_product", "Another reply in this thread already names the product. Use the value-first version here."
    gap = settings.min_thread_gap_minutes * 60
    stamps = [r.published_at or r.updated_at for r in sent if r.status in ("published", "pending_manual_post")]
    if gap and stamps:
        wait = int(gap - ((now or time.time()) - max(stamps)))
        if wait > 0:
            return "thread_gap", f"Wait {wait // 60 + 1} more minutes before the next reply in this thread."
    return "ok", ""
