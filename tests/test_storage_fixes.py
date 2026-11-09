from __future__ import annotations

from agent_reach.discovery.models import DiscoveredItem
from agent_reach.mcp import server


def test_list_discovered_items_filters_and_limits(storage):
    for i, plat in enumerate(["reddit", "web", "reddit"]):
        storage.save_discovered_item(DiscoveredItem(url=f"https://example.com/{i}", platform=plat, title=f"t{i}"))
    assert len(storage.list_discovered_items(limit=2)) == 2
    assert {x.platform for x in storage.list_discovered_items(platform="reddit")} == {"reddit"}


def test_save_lead_finds_the_stored_thread_when_item_id_is_stale(svc, profile, thread):
    out = server.reach_save_lead(
        title=thread.title, url=thread.url, platform="reddit", community="r/freelance", customer_problem="x",
        evidence_quote="I keep chasing invoices every month", problem_fit=26, icp_match=20, buying_intent=16,
        urgency=10, item_id="id-that-does-not-exist",
    )
    assert out["saved"] and out["evidence_verified"] is True
