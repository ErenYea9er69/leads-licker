# -*- coding: utf-8 -*-
"""MCP tools for the company layer. The owner talks to the CEO. The CEO uses these tools.

Every tool is an MCP tool. None of them is a prompt. The CEO opens a directive, the team works
through verified tasks, and the report comes only from work that passed verification.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from agent_reach.mcp.compat import network, read_only, writes
from agent_reach.mcp.server import get_service, mcp
from agent_reach.team.engine import TeamEngine
from agent_reach.team.intake import Intake
from agent_reach.team.roles import WORKER_ONLY_TOOLS

log = logging.getLogger("agent_reach.mcp")

_engine: Optional[TeamEngine] = None


def get_intake() -> Intake:
    """The interview. It shares the engine and the server's current service."""
    return Intake(get_service, get_engine())


def get_engine() -> TeamEngine:
    """The shared engine. It follows the server's current service and storage."""
    global _engine
    if _engine is None:
        _engine = TeamEngine(get_service)
    return _engine


@mcp.tool(annotations=network("CEO: take a request from the owner"))
def ceo_open_directive(request: str, intent: str = "", playbook: str = "", auto_run: bool = True) -> Dict[str, Any]:
    """Start here for every owner request. The CEO plans the work as tasks for specialists.

    request: the owner's words, unchanged. intent: find_customers, draft_replies, review_drafts, weekly_review,
    setup_voice, market_research, follow_up, status or custom (leave empty to let the CEO decide).
    playbook: a named plan from ceo_list_team. auto_run: when the server has its own model, run the plan until
    it needs the owner. Without one, you act as the specialists: call ceo_next_step and follow it.
    The answer carries readiness notes (what the company lacks) and the task plan.
    """
    engine = get_engine()
    opened = engine.open_directive(request, intent=intent, playbook=playbook)
    if "error" in opened or not auto_run or opened.get("intent") == "status":
        return opened
    if not engine.llm_ready():
        return {**opened, "mode": "host", "next": "Call ceo_next_step with the directive_id and do what it says."}
    return {**opened, **engine.run(opened["directive_id"])}


@mcp.tool(annotations=network("CEO: interview the owner and start work while they answer"))
def ceo_intake(
    answers: Optional[Dict[str, str]] = None, skip: Optional[List[str]] = None, wait: bool = False
) -> Dict[str, Any]:
    """Run the owner interview. Call it at the start of a new project and after every answer the owner gives.

    answers: the owner's own words per question. Keys: product, target_users, problems, platforms, competitors,
    site, accounts, voice, language, rules, posting. Pass only what the owner said. Never fill a gap yourself.
    skip: question keys the owner declined. wait: true waits for the background search (tests and scripts only).

    The CEO starts the search on its own once it knows the product and the target users. The search runs in the
    background while you ask the next one or two questions in ask_next, so the owner never waits. Questions the
    search does not need come first while it runs. With a server model the CEO also starts the full plan.
    The answer lists the jobs and what they found, what to tell the owner, the next questions and
    actions_for_you (link accounts, store voice samples, set the language). Read tell_owner to the owner.
    """
    return get_intake().turn(answers, skip, wait=wait)


@mcp.tool(annotations=read_only("CEO: status of the company"))
def ceo_status(directive_id: str = "") -> Dict[str, Any]:
    """List recent directives, or show one directive with its tasks, status and recent events."""
    return get_engine().status(directive_id)


@mcp.tool(annotations=writes("CEO: the one next action for a directive"))
def ceo_next_step(directive_id: str) -> Dict[str, Any]:
    """Ask what to do now. The answer is one action: work, ask_owner, decide, run, report, wait or stop.

    Follow it exactly, then call this again. It also returns progress and puts stalled tasks back in the queue.
    """
    return get_engine().next_step(directive_id)


@mcp.tool(annotations=network("CEO: continue the plan on the server's model"))
def ceo_run(directive_id: str, max_tasks: int = 12) -> Dict[str, Any]:
    """Run ready tasks with the server's own model until the plan needs the owner, fails, or finishes.

    Needs an LLM key on the server. Without one, use ceo_next_work_order.
    """
    return get_engine().run(directive_id, max_tasks=max_tasks)


@mcp.tool(annotations=writes("CEO: hand out the next work order"))
def ceo_next_work_order(directive_id: str = "", task_id: str = "") -> Dict[str, Any]:
    """Get the brief for a specialist task: role prompt, instruction, inputs, allowed tools, output contract.

    Do the work as that specialist. Launch tools with ceo_call_tool, then hand in the result with ceo_submit_result.
    Pass directive_id for the next ready task, or task_id for one task.
    """
    return get_engine().work_order(directive_id=directive_id, task_id=task_id)


@mcp.tool(annotations=network("CEO: launch a tool for a specialist"))
def ceo_call_tool(task_id: str, tool: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Launch one tool inside a task. The task's role decides which tools are allowed.

    The result carries an evidence_id. Cite it in your claims. Restricted tools (publish, approve, settings) are refused.
    """
    return get_engine().call_tool(task_id, tool, args or {})


@mcp.tool(annotations=writes("CEO: hand in a specialist result for verification"))
def ceo_submit_result(task_id: str, result: Dict[str, Any]) -> Dict[str, Any]:
    """Hand in the result of a task. The verifier checks it and answers accepted or a list of issues.

    result: {"summary": "...", "claims": [{"text": "...", "evidence_ids": ["E1"], "quote": "..."}], "data": {...}}.
    Fix every issue and submit again. After three failed tries the task goes back to the CEO.
    """
    return get_engine().submit_result(task_id, result)


@mcp.tool(annotations=writes("CEO: record the owner's answer to a checkpoint"))
def ceo_resolve_checkpoint(task_id: str, decision: str, owner_message: str) -> Dict[str, Any]:
    """Record the owner's decision on a checkpoint such as confirming the profile.

    decision: approve or reject. owner_message: the owner's own words. Ask the owner. Never answer for them.
    A rejection sends the work back to the specialist with the owner's feedback.
    """
    return get_engine().resolve_checkpoint(task_id, decision, owner_message)


@mcp.tool(annotations=writes("CEO: add a task to a directive"))
def ceo_create_task(
    directive_id: str,
    role: str,
    title: str,
    instruction: str = "",
    depends_on: Optional[List[str]] = None,
    acceptance: Optional[List[str]] = None,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """Create a task for a specialist. The instruction becomes part of that specialist's brief.

    depends_on: task ids that must finish first. acceptance: short checks the output must meet.
    """
    return get_engine().create_task(directive_id, role, title, instruction, depends_on, acceptance, max_attempts)


@mcp.tool(annotations=writes("CEO: retry, reassign or skip a task"))
def ceo_update_task(task_id: str, action: str, instruction: str = "", role: str = "", reason: str = "") -> Dict[str, Any]:
    """Decide what happens to a task. action: retry (optionally with a new instruction), reassign (needs role) or skip."""
    return get_engine().update_task(task_id, action, instruction=instruction, role=role, reason=reason)


@mcp.tool(annotations=writes("CEO: hire a new specialist"))
def ceo_hire_specialist(
    name: str,
    title: str,
    charter: str,
    skills: Optional[List[str]] = None,
    tools: Optional[List[str]] = None,
    tier: str = "smart",
) -> Dict[str, Any]:
    """Create a specialist with its own prompt and tool list. Restricted tools are never allowed.

    charter: what it does and what it never does. skills: names from reach_list_skills. tools: names from ceo_list_team.
    """
    return get_engine().hire_specialist(name, title, charter, skills, tools, tier)


@mcp.tool(annotations=writes("CEO: save a reusable plan"))
def ceo_create_playbook(name: str, description: str, steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Save a plan for repeated requests. Each step: {key, role, title, instruction, depends_on: [keys], acceptance: [...]}.

    A step with kind "checkpoint" waits for the owner. Use the plan later with ceo_open_directive(playbook=name).
    """
    return get_engine().create_playbook(name, description, steps)


@mcp.tool(annotations=read_only("CEO: the team, tools and plans"))
def ceo_list_team(include_tools: bool = False) -> Dict[str, Any]:
    """List the specialists with their tools, the saved plans, and (when asked) every tool a specialist may hold."""
    engine = get_engine()
    data = engine.describe_team()
    if include_tools:
        data["tool_catalog"] = engine.toolbox.catalog()
    return data


@mcp.tool(annotations=writes("CEO: stop a directive"))
def ceo_cancel_directive(directive_id: str, reason: str = "") -> Dict[str, Any]:
    """Cancel an unfinished directive when the owner says stop. Open tasks end. Verified work stays in the report."""
    return get_engine().cancel_directive(directive_id, reason)


@mcp.tool(annotations=writes("CEO: company memory"))
def ceo_memory(action: str = "list", text: str = "", memory_id: int = 0) -> Dict[str, Any]:
    """Keep the owner's standing preferences and the team's lessons. action: list, add or forget.

    add stores the owner's preference (text, at least 8 characters) such as "never mention pricing in a first reply".
    Every specialist sees it in its work order. Memory guides the work. It is never evidence.
    """
    engine = get_engine()
    if action == "add":
        return engine.remember(text)
    if action == "forget":
        return engine.forget(memory_id)
    if action == "list":
        return engine.recall()
    return {"error": "action must be list, add or forget."}


@mcp.tool(annotations=read_only("CEO: report to the owner"))
def ceo_report(directive_id: str) -> Dict[str, Any]:
    """Report for the owner: headline, trust level, lead cards (thread, quote, draft, gate), what was tried when
    nothing was found, verified work, work that did not pass, stats and the owner's next actions.

    Only verified work appears as done. Show the headline and the lead cards. Do not add results of your own.
    """
    return get_engine().report(directive_id)


def apply_mode(mode: Optional[str] = None) -> str:
    """Company mode hides the specialist tools from the host. Full mode shows every tool.

    The specialist tools stay available to the team through the toolbox in both modes.
    """
    chosen = (mode or os.getenv("AGENT_REACH_MCP_MODE") or "company").strip().lower()
    if chosen not in ("company", "full"):
        chosen = "company"
    if chosen == "company":
        for name in sorted(WORKER_ONLY_TOOLS):
            try:
                mcp.remove_tool(name)
            except Exception:  # already removed, or not registered on this SDK line
                continue
    return chosen
