# -*- coding: utf-8 -*-
"""What each source needs: tokens, API keys, packages and limits. The owner asks the CEO about them.

This module reads the environment and the linked accounts. It reports variable NAMES and whether each is set.
It never returns a value, and it never stores one. Variables go in the environment that starts the MCP server,
for example the `env` block of the MCP client's config.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Dict, List, Optional

from agent_reach.discovery.accounts import AccountService, account_key

# Each source lists what works with no setup, then the optional or required variables.
CATALOG: Dict[str, Dict[str, Any]] = {
    "reddit": {
        "name": "Reddit",
        "without_setup": "Search works through the web search chain. Thread health (comment count, locked, archived) is often blocked without app credentials.",
        "read": [
            {"name": "REDDIT_CLIENT_ID", "required": False, "purpose": "Reads thread metadata with an app-only token."},
            {"name": "REDDIT_CLIENT_SECRET", "required": False, "purpose": "Pairs with the client id."},
        ],
        "post": "Posting through the API needs Reddit's approval for API access. Without it, the app hands you each approved reply and you post it yourself.",
        "post_variables": "Per account: REDDIT_<ALIAS>_CLIENT_ID, REDDIT_<ALIAS>_CLIENT_SECRET, REDDIT_<ALIAS>_USERNAME, REDDIT_<ALIAS>_PASSWORD. The first account also reads the plain names REDDIT_CLIENT_ID and so on. The username must equal the linked handle. Automatic posting also needs AGENT_REACH_ALLOW_AUTOPOST=1 and posting mode automatic.",
        "how_to_get": [
            "Sign in to the Reddit account and open reddit.com/prefs/apps.",
            "Create an app of type script. The id sits under the app name, the secret is labelled secret.",
            "Reddit requires approval for new API access. Read its Data API terms before you apply.",
        ],
        "limits": "Reddit rate limits API calls per client. The app waits between posts and caps posts per account per day.",
        "accounts": True,
    },
    "hackernews": {
        "name": "Hacker News",
        "without_setup": "Search and thread reading work with no key (the Algolia API).",
        "read": [],
        "post": "The app drafts no replies for Hacker News. Use it for research.",
        "how_to_get": [],
        "limits": "The public Algolia API limits requests per IP. A normal campaign stays far below it.",
        "accounts": False,
    },
    "web": {
        "name": "The web (forums, blogs, Q and A)",
        "without_setup": "Search works through Exa, then DuckDuckGo. Results are fewer and less fresh than with a keyed provider.",
        "read": [
            {"name": "SERPER_API_KEY", "required": False, "purpose": "Google results through serper.dev. Tried first."},
            {"name": "BRAVE_API_KEY", "required": False, "purpose": "Brave Search results. Tried second."},
            {"name": "TAVILY_API_KEY", "required": False, "purpose": "Tavily results. Tried third."},
        ],
        "post": "The app never posts to arbitrary sites. You post by hand.",
        "how_to_get": ["Create a free account at serper.dev, brave.com/search/api or tavily.com and copy the key."],
        "limits": "Each provider has a free monthly quota. Every search spends one call.",
        "accounts": False,
    },
    "youtube": {
        "name": "YouTube",
        "without_setup": "Videos come from the web search chain. They carry no comments and no verified comment state.",
        "read": [
            {"name": "YOUTUBE_API_KEY", "required": False, "purpose": "Search, comment counts, top comments and channel age through the Data API v3."},
            {"name": "YOUTUBE_DAILY_QUOTA", "required": False, "purpose": "Daily units the app may spend. Default 9000 of the 10000 Google grants."},
        ],
        "packages": [{"import": "youtube_transcript_api", "install": 'pip install "agent-reach[youtube]"', "purpose": "Reads transcripts and asks YouTube to translate them. No key."}],
        "post": "The app never posts to YouTube. The Data API needs OAuth consent for writes. You paste each comment from your own channel.",
        "how_to_get": [
            "Open console.cloud.google.com and create a project.",
            "Enable YouTube Data API v3 for the project.",
            "Create an API key under Credentials. Restrict it to YouTube Data API v3.",
        ],
        "limits": "A search costs 100 units. A video lookup or a comment page costs 1. At the default quota that is about 90 searches a day.",
        "accounts": True,
    },
    "twitter": {
        "name": "X (Twitter)",
        "without_setup": "Posts surface through the web search chain only. Coverage is thin.",
        "read": [],
        "post": "The app does not post to X. You post by hand from your own accounts.",
        "how_to_get": [],
        "limits": "Search engines index few posts. Treat X as a weak source.",
        "accounts": True,
    },
    "github": {
        "name": "GitHub issues",
        "without_setup": "Issue search works without a token at a low rate limit.",
        "read": [{"name": "GITHUB_TOKEN", "required": False, "purpose": "Raises the search rate limit."}],
        "post": "Posting a comment needs a token with permission to comment on public issues.",
        "post_variables": "Per account: GITHUB_<ALIAS>_TOKEN. The first account also reads GITHUB_TOKEN.",
        "how_to_get": ["Open github.com/settings/tokens, create a fine-grained token, allow issue comments on public repositories."],
        "limits": "Unauthenticated search allows about 10 requests a minute. A token allows about 30.",
        "accounts": True,
    },
    "quora": {
        "name": "Quora",
        "without_setup": "Questions surface through the web search chain.",
        "read": [],
        "post": "The app does not post to Quora. You post by hand.",
        "how_to_get": [],
        "limits": "Quora blocks scraping. Coverage depends on the search engine.",
        "accounts": True,
    },
    "model": {
        "name": "Server model (optional)",
        "without_setup": "Your assistant plays every specialist. Nothing is lost except background runs of the whole plan and the second-model audit.",
        "read": [
            {"name": "ANTHROPIC_API_KEY", "required": False, "purpose": "Runs the specialists on the server."},
            {"name": "OPENAI_API_KEY", "required": False, "purpose": "Alternative provider."},
            {"name": "GEMINI_API_KEY", "required": False, "purpose": "Alternative provider."},
            {"name": "GROQ_API_KEY", "required": False, "purpose": "Alternative provider."},
            {"name": "DEEPSEEK_API_KEY", "required": False, "purpose": "Alternative provider."},
        ],
        "post": "",
        "how_to_get": ["Create a key at your provider's console. One key is enough."],
        "limits": "The provider bills each call.",
        "accounts": False,
    },
}


def _is_set(name: str) -> bool:
    if os.getenv(name):
        return True
    if name == "YOUTUBE_API_KEY":
        from agent_reach.discovery.youtube import api_key

        return bool(api_key())
    return False


def _package(spec: Dict[str, str]) -> Dict[str, Any]:
    return {**spec, "installed": importlib.util.find_spec(spec["import"]) is not None}


def source_report(source: str, accounts: Optional[AccountService] = None) -> Dict[str, Any]:
    entry = CATALOG[source]
    read = [{**v, "set": _is_set(v["name"])} for v in entry["read"]]
    packages = [_package(p) for p in entry.get("packages", [])]
    report: Dict[str, Any] = {
        "source": source, "name": entry["name"], "works_without_setup": entry["without_setup"],
        "read_variables": read, "packages": packages, "posting": entry["post"],
        "how_to_get": entry["how_to_get"], "limits": entry["limits"],
    }
    if entry.get("post_variables"):
        report["posting_variables"] = entry["post_variables"]
    if source == "model":
        report["server_model_ready"] = any(v["set"] for v in read)
    if source == "youtube":
        report["search_with_api"] = _is_set("YOUTUBE_API_KEY")
        report["transcripts_ready"] = all(p["installed"] for p in packages)
    if accounts is not None and entry["accounts"]:
        linked = accounts.for_platform(source)
        report["accounts"] = [
            {"id": account_key(a), "mode": a.mode, "alias": a.alias or None, "credentials": accounts.credential_report(a)}
            for a in linked
        ]
        report["accounts_linked"] = len(linked)
    report["status"] = _status(report)
    return report


def _status(report: Dict[str, Any]) -> str:
    """ready: everything the source can use is set. partial: works, with limits. limited: weak without setup."""
    read = report["read_variables"]
    missing_read = [v for v in read if not v["set"]]
    packages_missing = [p for p in report["packages"] if not p["installed"]]
    accounts = report.get("accounts") or []
    unready = [a for a in accounts if not a["credentials"]["ready"] and a["credentials"]["posting"] == "api"]
    if not read and not report["packages"]:
        return "ready"
    if read and len(missing_read) == len(read) and report["source"] != "model":
        return "partial"
    if packages_missing or unready or missing_read:
        return "partial"
    return "ready"


def connections(source: str = "", accounts: Optional[AccountService] = None) -> Dict[str, Any]:
    """The full guide, or one source. Names and set or missing only."""
    key = (source or "").lower().strip()
    aliases = {"x": "twitter", "hn": "hackernews", "yt": "youtube", "llm": "model", "search": "web"}
    key = aliases.get(key, key)
    if key and key not in CATALOG:
        return {"error": f"Unknown source {source}.", "sources": sorted(CATALOG)}
    keys: List[str] = [key] if key else list(CATALOG)
    return {
        "sources": [source_report(k, accounts) for k in keys],
        "where_to_set_variables": (
            "Put each variable in the environment that starts the MCP server. In an MCP client config that is the "
            "`env` block of the agent-reach server entry, then restart the client. The app never stores a token or "
            "a password, and this answer never shows a value."
        ),
        "several_accounts": (
            "Link as many accounts per platform as you own with reach_link_account. Give each an alias. The alias "
            "names its variables: alias alt1 on Reddit reads REDDIT_ALT1_CLIENT_ID and REDDIT_ALT1_PASSWORD."
        ),
    }
