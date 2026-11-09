#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verification harness for all 8 Agent Reach Operating Modes (Modes A through H)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from agent_reach.cli import _generate_mcp_config
from agent_reach.discovery.storage import DiscoveryStorage
from agent_reach.mcp import server
from agent_reach.mcp.compat import make_server
from agent_reach.server.app import app


class TestAllOperatingModes(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # ── Mode A: Standalone Web Application ──
    def test_mode_a_standalone_web_application(self):
        """Mode A: Web frontend is served cleanly with SPA router fallback."""
        res_root = self.client.get("/")
        self.assertEqual(res_root.status_code, 200)
        self.assertIn("text/html", res_root.headers.get("content-type", ""))
        self.assertIn("<div id=\"root\">", res_root.text)

        # SPA router fallback for subpaths
        res_spa = self.client.get("/team")
        self.assertEqual(res_spa.status_code, 200)
        self.assertIn("<div id=\"root\">", res_spa.text)
        print("[PASS] Mode A: Standalone Web Application verified.")

    # ── Mode B: Standalone Backend and API ──
    def test_mode_b_standalone_backend_and_api(self):
        """Mode B: Headless REST API, OpenAPI docs, and system diagnostics."""
        res_health = self.client.get("/api/health")
        self.assertEqual(res_health.status_code, 200)
        data = res_health.json()
        self.assertIn(data["status"], ("ok", "degraded"))
        self.assertEqual(data["database"], "connected")

        res_status = self.client.get("/api/system/status")
        self.assertEqual(res_status.status_code, 200)
        status_data = res_status.json()
        self.assertEqual(status_data["status"], "ready")
        self.assertTrue(status_data["mcp_mounted"])

        # Interactive OpenAPI documentation and schema
        res_docs = self.client.get("/docs")
        self.assertEqual(res_docs.status_code, 200)
        self.assertIn("text/html", res_docs.headers.get("content-type", ""))

        res_openapi = self.client.get("/openapi.json")
        self.assertEqual(res_openapi.status_code, 200)
        schema = res_openapi.json()
        self.assertIn("openapi", schema)
        self.assertIn("/api/health", schema["paths"])
        print("[PASS] Mode B: Standalone Backend & API verified.")

    # ── Mode C: Standalone MCP Server ──
    def test_mode_c_standalone_mcp_server(self):
        """Mode C: Standalone MCP Server operates without web frontend."""
        mcp_srv = server.create_mcp_server(mode="company")
        tools = asyncio.run(mcp_srv.list_tools())
        tool_names = {t.name for t in tools}

        self.assertIn("ceo_open_directive", tool_names)
        self.assertIn("ceo_status", tool_names)
        self.assertIn("reach_status", tool_names)
        self.assertIn("reach_browser_status", tool_names)

        # Execute MCP tool directly
        status_res = server.reach_status()
        self.assertIn("leads", status_res)
        print("[PASS] Mode C: Standalone MCP Server verified.")

    # ── Mode D: Web Application + MCP Synchronized ──
    def test_mode_d_web_app_plus_mcp_synchronized(self):
        """Mode D: Frontend API and MCP server share identical live SQLite state."""
        # Update business profile via MCP tool
        profile_res = server.reach_get_or_create_profile(
            name="OmniSync",
            url="https://omnisync.example",
            description="Universal data synchronization engine for SaaS platforms",
        )
        self.assertEqual(profile_res["name"], "OmniSync")

        # Read the exact profile back via FastAPI REST endpoint
        api_res = self.client.get("/api/profile")
        self.assertEqual(api_res.status_code, 200)
        api_data = api_res.json()
        self.assertIsNotNone(api_data["profile"])
        self.assertEqual(api_data["profile"]["name"], "OmniSync")
        print("[PASS] Mode D: Web App + MCP Synchronized state verified.")

    # ── Mode E: Claude Desktop + MCP ──
    def test_mode_e_claude_desktop_config(self):
        """Mode E: Valid configuration snippet generated for Claude Desktop."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            code = _generate_mcp_config("claude-desktop")
        self.assertEqual(code, 0)
        cfg = json.loads(f.getvalue())
        self.assertIn("agent-reach", cfg["mcpServers"])
        self.assertEqual(cfg["mcpServers"]["agent-reach"]["args"], ["-m", "agent_reach.cli", "mcp"])
        print("[PASS] Mode E: Claude Desktop + MCP configuration verified.")

    # ── Mode F: Claude Web + Remote MCP ──
    def test_mode_f_claude_web_remote_mcp(self):
        """Mode F: Remotely hosted MCP server mounted with token authentication."""
        old_key = os.environ.get("AGENT_REACH_API_KEY")
        try:
            os.environ["AGENT_REACH_API_KEY"] = "remote-token-xyz"
            # Unauthenticated access to /api or /mcp rejected
            res_unauth = self.client.get("/api/profile")
            self.assertEqual(res_unauth.status_code, 401)

            # Authenticated access succeeds
            res_auth = self.client.get("/api/profile", headers={"Authorization": "Bearer remote-token-xyz"})
            self.assertEqual(res_auth.status_code, 200)
        finally:
            if old_key is None:
                os.environ.pop("AGENT_REACH_API_KEY", None)
            else:
                os.environ["AGENT_REACH_API_KEY"] = old_key
        print("[PASS] Mode F: Claude Web + Remote MCP verified.")

    # ── Mode G: Claude Code / CLI + MCP ──
    def test_mode_g_claude_code_and_cli(self):
        """Mode G: CLI registration command and doctor diagnostics."""
        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            code = _generate_mcp_config("claude-code")
        self.assertEqual(code, 0)
        self.assertIn("claude mcp add agent-reach --", f.getvalue())
        print("[PASS] Mode G: Claude Code / CLI + MCP verified.")

    # ── Mode H: Other MCP Clients (Cursor, Windsurf) ──
    def test_mode_h_other_mcp_clients(self):
        """Mode H: Generic MCP client config for Cursor, Windsurf, and SSE."""
        import io
        from contextlib import redirect_stdout

        for client in ("cursor", "windsurf", "remote"):
            f = io.StringIO()
            with redirect_stdout(f):
                code = _generate_mcp_config(client)
            self.assertEqual(code, 0)
            cfg = json.loads(f.getvalue())
            self.assertIn("mcpServers", cfg)
        print("[PASS] Mode H: Other MCP Clients compatibility verified.")


if __name__ == "__main__":
    unittest.main()
