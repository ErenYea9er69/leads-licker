# -*- coding: utf-8 -*-
"""Console entry point for `agent-reach`.

    agent-reach mcp [--mode company|full]   MCP server over stdio
    agent-reach team ...                    talk to the CEO from the terminal
    agent-reach discovery ...               the step by step pipeline
    agent-reach dashboard                   the API for the dashboard (needs the dashboard extra)
    agent-reach doctor                      check the install
    agent-reach version
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import List, Optional, Sequence

from agent_reach import __version__

HELP = """leads-licker: finds customers in public communities and drafts honest replies.

  leads-licker mcp [--mode company|full]  run the MCP server over stdio (Claude, Cursor, VS Code, Antigravity)
  leads-licker team <command>             talk to the CEO: ask, status, run, report, checkpoint, roster
  leads-licker discovery <command>        step by step pipeline: profile, plan, search, leads, reply, lint, approve, post,
                                         confirm, voice, prefs, accounts, rules, posting, skills, check, export, analytics
  leads-licker dashboard [--port N]       API for the dashboard (pip install "leads-licker[dashboard]")
  leads-licker doctor                     check the install and the keys
  leads-licker version

Output is JSON. Add -v for logs on stderr.
"""


def _ensure_utf8_console() -> None:
    if sys.platform != "win32" or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        import io

        for name in ("stdout", "stderr"):
            stream = getattr(sys, name)
            if hasattr(stream, "buffer"):
                setattr(sys, name, io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace"))
    except Exception:
        pass


def _generate_mcp_config(target: str) -> int:
    py_exec = sys.executable
    target = target.strip().lower()
    if target in ("claude-desktop", "desktop"):
        cfg = {
            "mcpServers": {
                "agent-reach": {
                    "command": py_exec,
                    "args": ["-m", "agent_reach.cli", "mcp"],
                }
            }
        }
        print(json.dumps(cfg, indent=2))
        return 0
    if target in ("claude-code", "claude"):
        print(f"claude mcp add agent-reach -- {py_exec} -m agent_reach.cli mcp")
        return 0
    if target in ("cursor", ".cursor"):
        cfg = {
            "mcpServers": {
                "agent-reach": {
                    "command": py_exec,
                    "args": ["-m", "agent_reach.cli", "mcp"]
                }
            }
        }
        print(json.dumps(cfg, indent=2))
        return 0
    if target in ("windsurf", "codeium"):
        cfg = {
            "mcpServers": {
                "agent-reach": {
                    "command": py_exec,
                    "args": ["-m", "agent_reach.cli", "mcp"]
                }
            }
        }
        print(json.dumps(cfg, indent=2))
        return 0
    if target in ("remote", "sse"):
        cfg = {
            "mcpServers": {
                "agent-reach-remote": {
                    "url": "http://127.0.0.1:8001/sse",
                    "transport": "sse"
                }
            }
        }
        print(json.dumps(cfg, indent=2))
        return 0
    print(f"Unknown target: {target}. Supported targets: claude-desktop, claude-code, cursor, windsurf, remote.")
    return 1


def _cmd_mcp(args: Sequence[str]) -> int:
    if args and args[0] == "config":
        target = args[1] if len(args) > 1 else "claude-desktop"
        return _generate_mcp_config(target)

    parser = argparse.ArgumentParser(prog="agent-reach mcp", description="Run the MCP server.")
    parser.add_argument(
        "--mode", choices=["company", "full"], default=None,
        help="company (default): the host talks to the CEO tools. full: every low level tool is visible too.",
    )
    parser.add_argument(
        "--transport", choices=["stdio", "sse", "streamable-http"], default="stdio",
        help="Transport protocol: stdio (default) for local clients, sse or streamable-http for remote/network.",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Host address to bind to for sse / streamable-http (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port", type=int, default=8001,
        help="Port number for sse / streamable-http (default: 8001).",
    )
    ns = parser.parse_args(list(args))
    from agent_reach.mcp import server

    if ns.mode:
        os.environ["AGENT_REACH_MCP_MODE"] = ns.mode
    server.main(transport=ns.transport, host=ns.host, port=ns.port, mode=ns.mode)
    return 0


def _cmd_doctor(_: Sequence[str]) -> int:
    from agent_reach.discovery import skillpack
    from agent_reach.discovery.llm_client import LLMClient
    from agent_reach.discovery.storage import DEFAULT_DB_PATH

    report: dict = {"version": __version__, "python": sys.version.split()[0]}
    try:
        from importlib.metadata import version

        report["mcp_sdk"] = version("mcp")
    except Exception:
        report["mcp_sdk"] = "missing"
    llm = LLMClient()
    report["model"] = {"provider": llm.provider or None, "configured": llm.is_configured, "mode": "server" if llm.is_configured else "host"}
    report["search_keys"] = {k: bool(os.getenv(k)) for k in ("SERPER_API_KEY", "BRAVE_API_KEY", "TAVILY_API_KEY")}
    report["database"] = str(os.getenv("AGENT_REACH_DISCOVERY_DB") or DEFAULT_DB_PATH)
    try:
        report["skills"] = len(skillpack.list_skills())
    except Exception as exc:
        report["skills"] = f"error: {exc}"
    try:
        import asyncio

        from agent_reach.mcp import server

        report["mcp_tools_full"] = len(asyncio.run(server.mcp.list_tools()))
    except Exception as exc:
        report["mcp_tools_full"] = f"error: {exc}"
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401

        report["dashboard"] = "installed"
    except ImportError:
        report["dashboard"] = 'not installed (pip install "agent-reach[dashboard]")'
    print(json.dumps(report, indent=2))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> None:
    _ensure_utf8_console()
    args: List[str] = list(sys.argv[1:] if argv is None else argv)
    verbose = any(a in ("-v", "--verbose") for a in args)
    args = [a for a in args if a not in ("-v", "--verbose")]
    import logging

    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, stream=sys.stderr)

    if not args or args[0] in ("help", "-h", "--help"):
        sys.stdout.write(HELP)
        sys.exit(0)
    head, rest = args[0], args[1:]
    if head == "version":
        print(__version__)
        sys.exit(0)
    if head == "mcp":
        sys.exit(_cmd_mcp(rest))
    if head == "doctor":
        sys.exit(_cmd_doctor(rest))
    if head == "team":
        from agent_reach.team.cli import cmd_team

        sys.exit(cmd_team(rest))
    if head == "dashboard":
        from agent_reach.discovery.cli import cmd_dashboard

        sys.exit(cmd_dashboard(rest))
    if head in ("discovery", "lead-gen"):
        from agent_reach.discovery.cli import cmd_discovery

        sys.exit(cmd_discovery(rest))
    print(json.dumps({"error": f"Unknown command: {head}", "hint": "Run `leads-licker help`."}))
    sys.exit(1)


if __name__ == "__main__":
    main()
