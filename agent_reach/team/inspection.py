# -*- coding: utf-8 -*-
"""The posting inspection. It runs by itself at the end of a plan. No model and no assistant is involved.

It answers one question per draft: would this reply pass every posting gate if you approved it today?
The gate runs as if the owner had approved the draft and as if posting were switched on, because a draft
that is not approved yet always stops at the approval gate and shows nothing else.
It also checks that the draft was not edited after the editor read it and that its lead still has a verified quote.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from agent_reach.team.models import Directive, Task

# These stop a post for a while. The owner waits instead of fixing something.
WAIT_CODES = frozenset({"daily_cap", "interval", "thread_gap"})
INSPECTED_STATUSES = ("draft", "approved", "pending_manual_post")


def preflight_gate(svc: Any, reply: Any, lead: Any) -> Tuple[str, str]:
    """The gate result the reply would get if the owner approved it and posting were on."""
    settings = svc.storage.get_posting_settings()
    if settings.mode == "draft":
        settings = settings.model_copy(update={"mode": "manual"})
    if reply.status == "draft":
        reply = reply.model_copy(update={"status": "approved"})
    return svc.publisher.gate(reply, lead, settings)


def inspect(svc: Any, directive: Directive, tasks: List[Task]) -> List[Dict[str, Any]]:
    """One row per reply this directive touched. Everything in a row comes from the database and the gate."""
    storage = svc.storage
    reviewed: Dict[str, str] = {}
    review_time = 0.0
    editors = [t for t in tasks if t.role == "editor" and t.status == "done" and t.result]
    if editors:
        last = max(editors, key=lambda t: t.updated_at)
        review_time = last.updated_at
        for row in ((last.result or {}).get("data") or {}).get("reviews") or []:
            if isinstance(row, dict):
                reviewed[str(row.get("reply_id"))] = str(row.get("verdict", ""))
    rows: List[Dict[str, Any]] = []
    for reply in storage.list_replies(limit=300):
        if reply.updated_at < directive.created_at - 1 or reply.status not in INSPECTED_STATUSES:
            continue
        lead = storage.get_lead(reply.lead_id)
        if lead is None:
            continue
        code, message = preflight_gate(svc, reply, lead)
        verdict = reviewed.get(reply.id, "")
        edited = bool(review_time) and reply.updated_at > review_time + 1
        attention: List[str] = []
        if edited:
            attention.append("The draft changed after the editor read it. Read it again.")
        if not lead.evidence_verified:
            attention.append("The lead's quote is not verified against the thread.")
        if verdict == "revise":
            attention.append("The editor still asks for changes.")
        rows.append({
            "reply_id": reply.id,
            "lead_id": lead.id,
            "title": lead.title[:100],
            "community": lead.community,
            "code": code,
            "message": message,
            "ready": code == "ok" and not attention,
            "waits": code in WAIT_CODES,
            "editor_verdict": verdict,
            "attention": attention,
        })
    rows.sort(key=lambda r: (not r["ready"], r["code"], r["reply_id"]))
    return rows


def summarize(rows: List[Dict[str, Any]]) -> str:
    ready = sum(1 for r in rows if r["ready"])
    blocked = sum(1 for r in rows if r["code"] != "ok")
    attention = sum(1 for r in rows if r["attention"])
    return (
        f"Inspected {len(rows)} draft(s): {ready} would pass the posting gates today, "
        f"{blocked} are blocked by a gate, {attention} need a second look."
    )
