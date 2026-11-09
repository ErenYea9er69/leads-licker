# -*- coding: utf-8 -*-
"""Command line for AI customer discovery.

    agent-reach discovery profile --url https://example.com
    agent-reach discovery plan
    agent-reach discovery search --max 10
    agent-reach discovery leads --min-score 60
    agent-reach discovery reply LEAD_ID --target auto
    agent-reach discovery lint --text "..." --kind product_aware
    agent-reach discovery approve REPLY_ID
    agent-reach discovery post REPLY_ID
    agent-reach discovery confirm REPLY_ID --url https://...
    agent-reach discovery voice --from-account reddit:handle
    agent-reach discovery accounts link|list|refresh|health|unlink
    agent-reach discovery rules set r/sub --self-promo thread_only
    agent-reach discovery posting show|set|stop|resume
    agent-reach discovery skills list|show|manifest
    agent-reach discovery check llm|search|youtube|connections

Every command prints JSON. Errors print {"error": "..."} and exit with code 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence

from agent_reach.discovery.accounts import AccountError
from agent_reach.discovery.analytics import DiscoveryAnalytics
from agent_reach.discovery.models import CommunityRule
from agent_reach.discovery.orchestrator import DiscoveryOrchestrator
from agent_reach.discovery.reply_generator import ReplyGenerationError, ReplyLintError
from agent_reach.discovery.storage import DiscoveryStorage


def _out(data: Any) -> int:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))
    return 0


def _fail(message: str, **extra: Any) -> int:
    print(json.dumps({"error": message, **extra}, indent=2, ensure_ascii=False))
    return 1


def _progress(message: str, percent: int) -> None:
    sys.stderr.write(f"[{percent}%] {message}\n")


def _platform_handle(text: str) -> tuple:
    if ":" not in text:
        raise ValueError("Use platform:handle, for example reddit:my_name.")
    platform, handle = text.split(":", 1)
    return platform.strip().lower(), handle.strip()


def cmd_dashboard(args: Sequence[str]) -> int:
    """Launch the dashboard server when the dashboard module is installed."""
    parser = argparse.ArgumentParser(prog="agent-reach dashboard")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    ns = parser.parse_args(list(args))
    try:
        import uvicorn

        import agent_reach.server.app  # noqa: F401
    except ImportError as exc:
        return _fail(
            "The dashboard needs extra packages.",
            detail=str(exc),
            hint='Run: pip install "agent-reach[dashboard]". Or use the CLI or the MCP server.',
        )
    print(f"Starting dashboard at http://{ns.host}:{ns.port}")
    uvicorn.run("agent_reach.server.app:app", host=ns.host, port=ns.port, log_level="info")
    return 0


# ── Handlers ──────────────────────────────────────────────────────────────────

def _profile(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery profile")
    p.add_argument("--url")
    p.add_argument("--name")
    p.add_argument("--desc")
    p.add_argument("--confirm", action="store_true", help="Mark the stored profile as confirmed")
    ns = p.parse_args(rest)
    if ns.url:
        profile = o.business_engine.analyze_website(ns.url)
    elif ns.desc:
        profile = o.business_engine.analyze_manual_description(ns.desc, name=ns.name)
    else:
        stored = o.storage.get_latest_business_profile()
        if not stored:
            return _fail("No business profile found. Provide --url or --desc.")
        profile = stored
    if ns.confirm:
        profile.confirmed = True
    o.storage.save_business_profile(profile)
    return _out(profile.model_dump())


def _plan(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    from agent_reach.discovery.search_planner import SearchPlanner

    p = argparse.ArgumentParser(prog="agent-reach discovery plan")
    p.add_argument("--platforms", default="reddit,hackernews,web")
    p.add_argument("--communities", default="", help="Comma list of subreddits, for example r/freelance,r/smallbusiness")
    ns = p.parse_args(rest)
    profile = o.storage.get_latest_business_profile()
    if not profile:
        return _fail("No business profile found. Run `agent-reach discovery profile` first.")
    queries = SearchPlanner(o.llm).plan_queries(
        profile, _csv(ns.platforms), _csv(ns.communities) or None
    )
    return _out([q.model_dump() for q in queries])


def _csv(text: str) -> List[str]:
    return [t.strip() for t in (text or "").split(",") if t.strip()]


def _search(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery search")
    p.add_argument("--max", type=int, default=10)
    p.add_argument("--name", default="CLI Campaign")
    p.add_argument("--platforms", default="reddit,hackernews,web")
    p.add_argument("--communities", default="")
    ns = p.parse_args(rest)
    try:
        campaign = o.run_campaign_sync(
            campaign_name=ns.name,
            platforms=_csv(ns.platforms),
            max_leads=ns.max,
            progress_callback=_progress,
            communities=_csv(ns.communities) or None,
        )
    except Exception as exc:
        return _fail(str(exc))
    return _out(campaign.model_dump())


def _leads(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery leads")
    p.add_argument("--min-score", type=int, default=50)
    p.add_argument("--platform")
    ns = p.parse_args(rest)
    leads = o.storage.list_leads(min_score=ns.min_score, platform=ns.platform)
    return _out([lead.model_dump() for lead in leads])


def _reply(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery reply")
    p.add_argument("lead_id")
    p.add_argument("--target", choices=("auto", "post", "comment"), default="auto")
    p.add_argument("--comment-id", default="")
    p.add_argument("--regenerate", action="store_true")
    ns = p.parse_args(rest)
    lead = o.storage.get_lead(ns.lead_id)
    if not lead:
        return _fail(f"Lead {ns.lead_id} not found.")
    reply = None if ns.regenerate else o.storage.get_reply_by_lead_id(ns.lead_id)
    if reply is None:
        try:
            reply = o.draft_for_lead(lead, target_mode=ns.target, comment_id=ns.comment_id)
        except ReplyGenerationError as exc:
            return _fail(str(exc))
    return _out(reply.model_dump())


def _lint(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery lint")
    p.add_argument("--text")
    p.add_argument("--file")
    p.add_argument("--kind", choices=("value_first", "product_aware", "custom"), default="value_first")
    p.add_argument("--level", type=int)
    p.add_argument("--platform", default="reddit")
    ns = p.parse_args(rest)
    text = ns.text if ns.text is not None else (Path(ns.file).read_text(encoding="utf-8") if ns.file else sys.stdin.read())
    profile = o.storage.get_latest_business_profile()
    from agent_reach.discovery.models import BusinessProfile

    report = o.reply_generator.check_text(
        text, kind=ns.kind, profile=profile or BusinessProfile(), prefs=o.get_prefs(),
        level=ns.level, platform=ns.platform, previous=o._previous_texts(),
    )
    return _out(report.to_dict())


def _approve(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery approve")
    p.add_argument("reply_id")
    p.add_argument("--version", choices=("value_first", "product_aware", "custom"))
    p.add_argument("--text", help="Your edited text. Use with --version custom.")
    p.add_argument("--force", action="store_true", help="Approve even when the linter reports errors")
    ns = p.parse_args(rest)
    try:
        reply = o.approve_reply(ns.reply_id, ns.text, ns.version, force=ns.force)
    except ReplyLintError as exc:
        return _fail("The text breaks writing rules.", issues=exc.issues)
    except (KeyError, ValueError) as exc:
        return _fail(str(exc))
    return _out(reply.model_dump())


def _post(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery post")
    p.add_argument("reply_id")
    ns = p.parse_args(rest)
    reply = o.storage.get_reply(ns.reply_id)
    if not reply:
        return _fail(f"Reply {ns.reply_id} not found.")
    lead = o.storage.get_lead(reply.lead_id)
    if not lead:
        return _fail("The lead for this reply is missing.")
    result = o.publisher.publish_or_copy(reply, lead, o.storage.get_posting_settings())
    _out(result)
    return 0 if result.get("success") else 1


def _confirm(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery confirm")
    p.add_argument("reply_id")
    p.add_argument("--url", default="", help="Link to your posted comment")
    ns = p.parse_args(rest)
    reply = o.storage.get_reply(ns.reply_id)
    lead = o.storage.get_lead(reply.lead_id) if reply else None
    if not reply or not lead:
        return _fail("Reply or lead not found.")
    try:
        return _out(o.publisher.confirm_manual_post(reply, lead, ns.url))
    except ValueError as exc:
        return _fail(str(exc))


def _voice(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery voice")
    p.add_argument("--file", help="Text file with one comment per blank-line-separated block")
    p.add_argument("--from-account", help="platform:handle of a linked account, for example reddit:my_name")
    p.add_argument("--append", action="store_true")
    p.add_argument("--show", action="store_true")
    ns = p.parse_args(rest)
    if ns.from_account:
        try:
            platform, handle = _platform_handle(ns.from_account)
            return _out(o.import_voice_from_account(platform, handle))
        except (ValueError, AccountError) as exc:
            return _fail(str(exc))
    if ns.file:
        blocks = [b.strip() for b in Path(ns.file).read_text(encoding="utf-8").split("\n\n") if b.strip()]
        prefs = o.set_voice_samples(blocks, append=ns.append)
        return _out({"samples": len(prefs.voice_samples), "voice_card": prefs.voice_card})
    prefs = o.get_prefs()
    return _out({"samples": len(prefs.voice_samples), "voice_card": prefs.voice_card})


def _prefs(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery prefs")
    p.add_argument("--pitch-level", type=int, choices=(0, 1, 2, 3))
    p.add_argument("--persona", choices=("founder", "employee", "maker", "contributor"))
    p.add_argument("--max-words", type=int)
    p.add_argument("--language")
    p.add_argument("--allow-links", choices=("yes", "no"))
    p.add_argument("--ban", default="", help="Comma list of extra banned words")
    p.add_argument("--strict-avoid", choices=("yes", "no"))
    p.add_argument("--user-list", choices=("on", "off"), help="Use the owner's personal banned list")
    ns = p.parse_args(rest)
    prefs = o.get_prefs()
    if ns.pitch_level is not None:
        prefs.pitch_level = ns.pitch_level
    if ns.persona:
        prefs.persona = ns.persona  # type: ignore[assignment]
    if ns.max_words:
        prefs.max_words = ns.max_words
    if ns.language:
        prefs.language = ns.language
    if ns.allow_links:
        prefs.allow_links = ns.allow_links == "yes"
    if ns.ban:
        prefs.banned_words = sorted(set(prefs.banned_words) | {w.lower() for w in _csv(ns.ban)})
    if ns.strict_avoid:
        prefs.strict_avoid = ns.strict_avoid == "yes"
    if ns.user_list:
        prefs.use_user_banned_list = ns.user_list == "on"
    o.save_prefs(prefs)
    data = prefs.model_dump()
    data["voice_samples"] = f"{len(prefs.voice_samples)} stored"
    return _out(data)


def _accounts(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    if not rest:
        return _fail("Use: accounts link|list|refresh|health|unlink")
    action, tail = rest[0], rest[1:]
    profile = o.storage.get_latest_business_profile()
    name = profile.name if profile else ""
    try:
        if action == "list":
            return _out([a.model_dump() for a in o.accounts.list()])
        p = argparse.ArgumentParser(prog=f"agent-reach discovery accounts {action}")
        p.add_argument("account", help="platform:handle")
        if action == "link":
            p.add_argument("--mode", choices=("manual", "api"), default="manual")
        ns = p.parse_args(tail)
        platform, handle = _platform_handle(ns.account)
        if action == "link":
            acc = o.accounts.link(platform, handle, ns.mode)
            acc = o.accounts.refresh(platform, acc.handle, name)
            return _out({"account": acc.model_dump(), "health": o.accounts.health(platform, acc.handle, name).to_dict()})
        if action == "refresh":
            acc = o.accounts.refresh(platform, handle, name)
            return _out({"account": acc.model_dump(), "health": o.accounts.health(platform, handle, name).to_dict()})
        if action == "health":
            return _out(o.accounts.health(platform, handle, name).to_dict())
        if action == "unlink":
            return _out({"removed": o.accounts.unlink(platform, handle)})
    except (ValueError, AccountError) as exc:
        return _fail(str(exc))
    return _fail(f"Unknown accounts action: {action}")


def _rules(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    if not rest or rest[0] not in ("set", "list", "show"):
        return _fail("Use: rules set COMMUNITY [options] | rules list | rules show COMMUNITY")
    action, tail = rest[0], rest[1:]
    if action == "list":
        return _out([r.model_dump() for r in o.storage.list_community_rules()])
    p = argparse.ArgumentParser(prog=f"agent-reach discovery rules {action}")
    p.add_argument("community")
    if action == "set":
        p.add_argument("--self-promo", choices=("allowed", "thread_only", "banned", "unknown"), default="unknown")
        p.add_argument("--links", choices=("yes", "no"), default="no")
        p.add_argument("--ai-content", choices=("yes", "no"), default="yes", help="Does the community allow AI-written text")
        p.add_argument("--min-karma", type=int, default=0)
        p.add_argument("--notes", default="")
    ns = p.parse_args(tail)
    if action == "show":
        rule = o.storage.get_community_rule(ns.community)
        return _out(rule.model_dump() if rule else {"community": ns.community, "recorded": False})
    rule = CommunityRule(
        community=ns.community, self_promo=ns.self_promo, links_allowed=ns.links == "yes",
        ai_content_allowed=ns.ai_content == "yes", min_karma=ns.min_karma, notes=ns.notes,
    )
    o.storage.save_community_rule(rule)
    return _out(rule.model_dump())


def _posting(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    if not rest:
        rest = ["show"]
    action, tail = rest[0], rest[1:]
    settings = o.storage.get_posting_settings()
    if action == "show":
        pass
    elif action == "stop":
        settings.emergency_stop = True
    elif action == "resume":
        settings.emergency_stop = False
    elif action == "set":
        p = argparse.ArgumentParser(prog="agent-reach discovery posting set")
        p.add_argument("--mode", choices=("draft", "manual", "automatic"))
        p.add_argument("--daily-limit", type=int)
        p.add_argument("--min-interval", type=int, help="Seconds between posts")
        p.add_argument("--max-mention-ratio", type=float)
        p.add_argument("--require-rules-ack", choices=("yes", "no"))
        p.add_argument("--require-account-health", choices=("yes", "no"))
        ns = p.parse_args(tail)
        if ns.mode:
            settings.mode = ns.mode  # type: ignore[assignment]
        if ns.daily_limit is not None:
            settings.daily_limit = max(0, ns.daily_limit)
        if ns.min_interval is not None:
            settings.min_interval_seconds = max(0, ns.min_interval)
        if ns.max_mention_ratio is not None:
            settings.max_mention_ratio = max(0.0, min(1.0, ns.max_mention_ratio))
        if ns.require_rules_ack:
            settings.require_rules_ack = ns.require_rules_ack == "yes"
        if ns.require_account_health:
            settings.require_account_health = ns.require_account_health == "yes"
    else:
        return _fail("Use: posting show|set|stop|resume")
    o.storage.save_posting_settings(settings)
    data = settings.model_dump()
    for key in ("reddit_client_id", "reddit_client_secret", "reddit_username", "reddit_password", "github_token"):
        data.pop(key, None)
    return _out(data)


def _skills(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    from agent_reach.discovery import skillpack

    action = rest[0] if rest else "list"
    if action == "list":
        return _out([s.to_dict() for s in skillpack.list_skills()])
    if action == "manifest":
        return _out(skillpack.manifest())
    if action == "show" and len(rest) > 1:
        try:
            return _out(skillpack.get_skill(rest[1]).to_dict(with_body=True))
        except Exception as exc:
            return _fail(str(exc))
    return _fail("Use: skills list|manifest|show NAME")


def _check(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    what = rest[0] if rest else "llm"
    if what == "llm":
        return _out(o.llm.check())
    if what == "search":
        from agent_reach.discovery.search_backends import SearchChain

        chain = SearchChain()
        results = chain.search("how do you chase late invoices reddit", 3)
        return _out({
            "backends": [b.name for b in chain.backends],
            "results": len(results),
            "diagnostics": dict(chain.diagnostics),
            "sample": results[:1],
        })
    if what == "youtube":
        from agent_reach.discovery import youtube

        return _out(youtube.check(storage=o.storage))
    if what == "connections":
        from agent_reach.discovery import connections

        return _out(connections.connections(rest[1] if len(rest) > 1 else "", o.accounts))
    return _fail("Use: check llm|search|youtube|connections [source]")


def _export(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    p = argparse.ArgumentParser(prog="agent-reach discovery export")
    p.add_argument("--format", choices=("csv", "json"), default="json")
    p.add_argument("--min-score", type=int, default=0)
    ns = p.parse_args(rest)
    print(o.storage.export_leads_csv(ns.min_score) if ns.format == "csv" else o.storage.export_leads_json(ns.min_score))
    return 0


def _analytics(o: DiscoveryOrchestrator, rest: List[str]) -> int:
    return _out(DiscoveryAnalytics(o.storage).get_insights())


COMMANDS: Dict[str, Callable[[DiscoveryOrchestrator, List[str]], int]] = {
    "profile": _profile,
    "plan": _plan,
    "search": _search,
    "leads": _leads,
    "reply": _reply,
    "lint": _lint,
    "approve": _approve,
    "post": _post,
    "confirm": _confirm,
    "voice": _voice,
    "prefs": _prefs,
    "accounts": _accounts,
    "rules": _rules,
    "posting": _posting,
    "skills": _skills,
    "check": _check,
    "export": _export,
    "analytics": _analytics,
}


def cmd_discovery(args: Sequence[str]) -> int:
    """Run `agent-reach discovery <command>`."""
    if not args or args[0] in ("-h", "--help", "help"):
        print("Usage: agent-reach discovery <" + "|".join(COMMANDS) + "> [args]")
        return 0 if args else 1
    sub, rest = args[0], list(args[1:])
    handler = COMMANDS.get(sub)
    if handler is None:
        return _fail(f"Unknown discovery command: {sub}", commands=list(COMMANDS))
    orchestrator = DiscoveryOrchestrator(DiscoveryStorage())
    try:
        return handler(orchestrator, rest)
    except SystemExit:
        raise
    except Exception as exc:  # one handler failing must not print a traceback at the owner
        return _fail(f"{type(exc).__name__}: {str(exc)[:300]}")
