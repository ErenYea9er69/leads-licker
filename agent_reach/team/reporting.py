# -*- coding: utf-8 -*-
"""The owner's report. It is built from verified work and the database, never from model prose.

The report has a headline, lead cards (the thread, the quote, the draft, the gate result and the next move),
what was tried when nothing was found, a trust level per task and plain next actions for the owner.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agent_reach.team.models import Directive, Task
from agent_reach.team.verifier import is_nothing_found

TRUST_ORDER = {"high": 3, "medium": 2, "low": 1}


def trust_level(tasks: List[Task]) -> str:
    """The weakest link decides. One unverified or low trust task lowers the whole report."""
    work = [t for t in tasks if t.kind == "work" and t.status != "skipped"]
    if not work:
        return "none"
    if any(t.status != "done" for t in work):
        return "partial"
    levels = [t.verdict.trust if t.verdict else "medium" for t in work]
    return min(levels, key=lambda lv: TRUST_ORDER.get(lv, 2))


def quality_numbers(tasks: List[Task]) -> Dict[str, Any]:
    work = [t for t in tasks if t.kind == "work"]
    return {
        "tool_calls": sum(t.tool_calls for t in work),
        "failed_checks_before_pass": sum(max(0, t.attempts - 1) for t in work if t.status == "done"),
        "tasks_escalated": sum(1 for t in work if t.status == "escalated"),
        "tasks_skipped_for_empty_input": sum(1 for t in tasks if t.skipped_empty),
        "revision_rounds": sum(1 for t in work if t.round >= 1 and t.role == "writer"),
    }


def what_was_tried(tasks: List[Task]) -> List[str]:
    """When a search or a qualification came back empty, say exactly what ran."""
    lines: List[str] = []
    for t in tasks:
        if t.kind != "work" or not is_nothing_found(t.result):
            continue
        reason = str(((t.result or {}).get("data") or {}).get("reason", ""))
        calls = [e for e in t.evidence if e.ok]
        queries: List[str] = []
        for e in calls:
            for q in e.args.get("queries") or []:
                queries.append(str(q)[:80])
        extra = f" Queries: {'; '.join(queries[:6])}." if queries else ""
        lines.append(f"{t.role}: {reason or 'nothing qualified.'}{extra} ({len(calls)} tool call(s) ran.)")
    return lines


def inspection_rows(tasks: List[Task]) -> List[Dict[str, Any]]:
    """The inspector's rows, or an empty list when it did not run."""
    runs = [t for t in tasks if t.role == "inspector" and t.status == "done" and t.result]
    if not runs:
        return []
    latest = max(runs, key=lambda t: t.updated_at)  # a later inspection replaces an earlier one
    return list(((latest.result or {}).get("data") or {}).get("inspections") or [])


def lead_cards(storage: Any, directive: Directive, limit: int = 12, inspections: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """One card per lead saved while this directive ran. Everything on the card comes from the database."""
    cards: List[Dict[str, Any]] = []
    gates = {r["reply_id"]: r for r in inspections or []}
    leads = [lead for lead in storage.list_leads(limit=200) if lead.created_at >= directive.created_at - 1]
    leads.sort(key=lambda lead: lead.score, reverse=True)
    for lead in leads[:limit]:
        all_replies = storage.list_replies_for_lead(lead.id)
        reply = max(all_replies, key=lambda r: r.updated_at) if all_replies else None
        card: Dict[str, Any] = {
            "lead_id": lead.id,
            "title": lead.title[:140],
            "url": lead.url,
            "platform": lead.platform,
            "community": lead.community,
            "score": lead.score,
            "classification": lead.classification,
            "quote_verified": bool(lead.evidence_verified),
            "evidence_quote": (lead.evidence or "")[:240],
            "status": lead.status,
        }
        if reply is not None:
            card["reply"] = {
                "reply_id": reply.id, "status": reply.status, "pitch_level": reply.pitch_level,
                "value_first": reply.value_first, "product_aware": reply.product_aware,
                "account": reply.account_id or None, "target": reply.target_key,
                "lint_passed": all(bool(v.get("passed")) for v in (reply.lint or {}).values()) if reply.lint else None,
            }
            gate = gates.get(reply.id)
            if gate is not None:
                card["reply"]["gate"] = {
                    "code": gate["code"], "message": gate["message"], "ready": gate["ready"],
                    "waits": gate["waits"], "editor_verdict": gate["editor_verdict"], "attention": gate["attention"],
                }
            if len(all_replies) > 1:   # a thread can hold two or three replies, each on its own target
                card["other_replies"] = [
                    {
                        "reply_id": r.id, "status": r.status, "account": r.account_id or None, "target": r.target_key,
                        "target_author": r.target_author or None, "value_first": r.value_first,
                    }
                    for r in all_replies if r.id != reply.id
                ]
        cards.append(card)
    return cards


def headline(directive: Directive, tasks: List[Task], cards: List[Dict[str, Any]], trust: str) -> str:
    work = [t for t in tasks if t.kind == "work"]
    done = [t for t in work if t.status == "done"]
    open_items = [t for t in work if t.status not in ("done", "skipped")]
    if directive.status == "cancelled":
        return "The owner cancelled this request. Work that passed verification before that is listed below."
    if any(t.role == "scout" and is_nothing_found(t.result) for t in work):
        return "The search found no open threads that match. The report lists what ran, and what to change."
    if any(t.role == "qualifier" and is_nothing_found(t.result) for t in work):
        return "Threads came back, but none qualified as a real customer. The report lists why."
    parts = [f"{len(done)} of {len(done) + len(open_items)} task(s) passed verification"]
    if cards:
        high = sum(1 for c in cards if c["classification"] == "high_potential")
        parts.append(f"{len(cards)} lead(s) saved, {high} high potential")
        drafts = sum(1 for c in cards if c.get("reply"))
        if drafts:
            parts.append(f"{drafts} draft reply(ies) ready for your review")
    parts.append(f"trust level {trust}")
    return ". ".join(parts) + "."
