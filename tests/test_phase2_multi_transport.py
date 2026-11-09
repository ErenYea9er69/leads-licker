"""Tests for Phase 2: Multi-Transport MCP, Browser Tools, Storage Enhancements, and Remote Auth."""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from agent_reach.discovery.models import BusinessProfile, DiscoveredItem, GeneratedReply, LeadQualification
from agent_reach.discovery.storage import DiscoveryStorage
from agent_reach.mcp import server
from agent_reach.cli import _generate_mcp_config
from tests.conftest import run


def test_storage_get_lead_by_url_and_backup(tmp_path: Path):
    db_path = tmp_path / "primary.db"
    backup_path = tmp_path / "backups" / "primary_backup.db"
    storage = DiscoveryStorage(db_path)

    profile = BusinessProfile(
        name="Tidewatch", url="https://tidewatch.example", description="Invoice tracking for freelancers",
        problems_solved=["late invoices"], pain_vocabulary=["late invoices", "clients pay late"],
        features=["automatic invoice reminders"], confirmed=True,
    )
    storage.save_business_profile(profile)

    item = DiscoveredItem(
        url="https://www.reddit.com/r/freelance/comments/xyz123/invoicing_troubles/",
        platform="reddit",
        community="r/freelance",
        author="designer_dan",
        title="Invoicing is killing my freelance business",
        content="My clients pay late every month and late invoices are ruining cashflow. What automated tools do you use?",
    )
    storage.save_discovered_item(item)

    from agent_reach.discovery.qualifier import LeadQualifier
    qualifier = LeadQualifier()
    lead = qualifier.qualify(item, profile)
    assert lead is not None
    storage.save_lead(lead)

    found = storage.get_lead_by_url(item.url)
    assert found is not None
    assert found.id == lead.id
    assert found.platform == "reddit"

    # Canonical match with trailing slash variation
    found_slash = storage.get_lead_by_url(item.url + "/")
    assert found_slash is not None
    assert found_slash.id == lead.id

    # Test online backup
    saved_backup = storage.backup(backup_path)
    assert saved_backup.exists()
    assert saved_backup.stat().st_size > 0

    backup_storage = DiscoveryStorage(saved_backup)
    assert backup_storage.get_lead_by_url(item.url) is not None
    backup_storage.close()
    storage.close()


def test_mcp_browser_tools(svc, profile, tmp_path):
    # Test reach_browser_status
    status = server.reach_browser_status()
    assert status["status"] == "ready"
    assert status["profile_configured"] is True
    assert status["product_name"] == "Tidewatch"
    assert status["extension_compatible"] is True

    # Test reach_browser_capture
    captured = server.reach_browser_capture(
        url="https://news.ycombinator.com/item?id=999999",
        title="Ask HN: Tools for tracking late client invoices?",
        content="I keep chasing invoices every month and my clients pay late. Any automated tool that reminds them?",
        platform="hackernews",
        community="Ask HN",
        author="founder_bob",
        auto_qualify=True,
    )
    assert captured["ok"] is True
    assert "lead_id" in captured
    assert captured["score"] >= 0

    # Test reach_browser_prepare_reply
    lead_id = captured["lead_id"]
    reply_model = GeneratedReply(
        lead_id=lead_id,
        value_first="A clear payment schedule in contracts helps minimize delays.",
        product_aware="We built Tidewatch to automatically send polite invoice reminders.",
        status="approved",
    )
    svc.storage.save_reply(reply_model)

    prep = server.reach_browser_prepare_reply(
        url="https://news.ycombinator.com/item?id=999999",
        version="product_aware",
    )
    assert prep["lead_id"] == lead_id
    assert "Tidewatch" in prep["text"]
    assert prep["is_approved"] is True


def test_cli_mcp_config_generation(capsys):
    assert _generate_mcp_config("claude-desktop") == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert "agent-reach" in data["mcpServers"]
    assert data["mcpServers"]["agent-reach"]["args"] == ["-m", "agent_reach.cli", "mcp"]

    assert _generate_mcp_config("claude-code") == 0
    out_code = capsys.readouterr().out
    assert "claude mcp add agent-reach" in out_code

    assert _generate_mcp_config("cursor") == 0
    assert "agent-reach" in json.loads(capsys.readouterr().out)["mcpServers"]

    assert _generate_mcp_config("remote") == 0
    assert "agent-reach-remote" in json.loads(capsys.readouterr().out)["mcpServers"]


def test_remote_mcp_auth_and_security(monkeypatch, tmp_path):
    from agent_reach.server.app import app
    monkeypatch.setenv("AGENT_REACH_API_KEY", "secret-test-token")
    client = TestClient(app)

    # Missing API key should return 401
    res_unauth = client.get("/api/profile")
    assert res_unauth.status_code == 401

    # Valid Bearer token should pass security middleware
    res_auth = client.get("/api/profile", headers={"Authorization": "Bearer secret-test-token"})
    assert res_auth.status_code == 200

    # Valid X-API-Key should pass
    res_xkey = client.get("/api/profile", headers={"X-API-Key": "secret-test-token"})
    assert res_xkey.status_code == 200
