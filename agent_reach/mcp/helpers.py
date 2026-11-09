# -*- coding: utf-8 -*-
"""Helpers for MCP server: reports, file exports, settings, and dashboard process management."""

from __future__ import annotations

import datetime
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from agent_reach.discovery.models import BusinessProfile, LeadQualification
from agent_reach.discovery.storage import DiscoveryStorage

MCP_SETTINGS_KEY = "mcp_settings"

DEFAULT_MCP_SETTINGS: Dict[str, Any] = {
    "discovery_mode": "host_driven",  # "host_driven" | "built_in_auto"
    "default_output_format": "both",   # "markdown" | "json" | "both"
    "default_min_score": 70,
    "default_export_path": "./discovery_exports",
    "emergency_stop": False,
    "auto_launch_dashboard": False,
}


def _safe_cell(val: Any) -> str:
    """Escape formula characters and format markdown cell cleanly."""
    if val is None:
        return ""
    text = str(val).strip()
    if text and (text[0] in ("=", "+", "@") or (text[0] == "-" and not text[1:2].isdigit())):
        return f"'{text}"
    return text.replace("|", "\\|").replace("\n", " ")


def generate_markdown_report(
    leads: Sequence[LeadQualification],
    profile: Optional[BusinessProfile] = None,
) -> str:
    """Generate a clean, structured Markdown customer discovery report."""
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: List[str] = [
        "# Leads Licker: Customer Discovery Report",
        f"\n*Generated on {now_str}*",
        "",
    ]

    if profile:
        lines.extend([
            "## Target Business Profile",
            f"- **Product / Company:** {profile.name}",
            f"- **Description:** {profile.description or profile.main_product_or_service or 'N/A'}",
            f"- **Ideal Customer Profile (ICP):** {profile.icp or ', '.join(profile.target_roles) or 'All relevant buyers'}",
            f"- **Key Problems Solved:** {', '.join(profile.problems_solved[:3]) if profile.problems_solved else 'N/A'}",
            "",
        ])

    total_leads = len(leads)
    high_potential = sum(1 for lead in leads if getattr(lead.classification, "value", lead.classification) == "high_potential")
    avg_score = (sum(lead.score for lead in leads) / total_leads) if total_leads > 0 else 0

    lines.extend([
        "## Summary",
        f"- **Total Qualified Leads:** {total_leads}",
        f"- **High-Potential Leads:** {high_potential}",
        f"- **Average Lead Score:** {avg_score:.1f}/100",
        "",
        "## Top Leads",
        "",
        "| Rank | Title | Score | Class | Platform | Community | Intent | Urgency | Thread Link |",
        "| :--- | :---- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |",
    ])

    if not leads:
        lines.append("| - | *No leads matching criteria* | - | - | - | - | - | - | - |")
    else:
        for idx, lead in enumerate(sorted(leads, key=lambda x: x.score, reverse=True), 1):
            title = _safe_cell(lead.title[:80] + ("..." if len(lead.title) > 80 else ""))
            score = f"{lead.score}/100"
            cls_name = getattr(lead.classification, "value", str(lead.classification))
            platform = lead.platform or "web"
            community = lead.community or "-"
            intent = getattr(lead.purchase_intent, "value", str(lead.purchase_intent))
            urgency = getattr(lead.urgency, "value", str(lead.urgency))
            url = f"[{platform}]({lead.url})" if lead.url else "-"
            lines.append(f"| {idx} | {title} | {score} | {cls_name} | {platform} | {community} | {intent} | {urgency} | {url} |")

    lines.extend(["", "## Lead Details", ""])
    for idx, lead in enumerate(leads, 1):
        lines.extend([
            f"### #{idx}: {_safe_cell(lead.title)}",
            f"- **URL:** {lead.url}",
            f"- **Platform:** `{lead.platform}` | **Community:** `{lead.community}` | **Author:** `{lead.author or 'Unknown'}`",
            f"- **Score:** **{lead.score}/100** (`{getattr(lead.classification, 'value', lead.classification)}`)",
            f"- **Customer Problem:** {lead.customer_problem or 'N/A'}",
            f"- **Pain Category:** `{lead.pain_point_category or 'general'}` | **Intent:** `{getattr(lead.purchase_intent, 'value', lead.purchase_intent)}` | **Urgency:** `{getattr(lead.urgency, 'value', lead.urgency)}`",
            f"- **Key Evidence:** *\"{_safe_cell(lead.evidence or lead.excerpt or 'None')}\"*",
            f"- **Product Fit:** {lead.product_fit_explanation or 'N/A'}",
            f"- **Profile Match:** {lead.profile_match or 'N/A'}",
            "",
        ])

    return "\n".join(lines)


def export_results_files(
    storage: DiscoveryStorage,
    output_dir: Path,
    formats: str = "both",
    min_score: int = 0,
) -> Dict[str, str]:
    """Export qualified leads into markdown, json, or both.

    The folder must sit under the current directory, the home folder or the system temp folder.
    """
    resolved = output_dir.expanduser().resolve()
    roots = [Path.cwd().resolve(), Path.home().resolve(), Path(tempfile.gettempdir()).resolve()]
    if not any(resolved == r or r in resolved.parents for r in roots):
        raise ValueError(f"Choose a folder under {roots[0]} or {roots[1]}.")
    output_dir = resolved
    output_dir.mkdir(parents=True, exist_ok=True)
    leads = storage.list_leads(min_score=min_score, limit=500)
    profile = storage.get_latest_business_profile()

    exported: Dict[str, str] = {}
    chosen = formats.lower().strip()

    if chosen in ("markdown", "both"):
        md_text = generate_markdown_report(leads, profile)
        md_path = output_dir / "customer_discovery_report.md"
        md_path.write_text(md_text, encoding="utf-8")
        exported["markdown"] = str(md_path.resolve())

    if chosen in ("json", "both"):
        json_path = output_dir / "customer_discovery_leads.json"
        leads_data = [lead.model_dump() for lead in leads]
        json_path.write_text(json.dumps(leads_data, indent=2, ensure_ascii=False), encoding="utf-8")
        exported["json"] = str(json_path.resolve())

    return exported


def get_or_init_mcp_settings(storage: DiscoveryStorage) -> Dict[str, Any]:
    """Load MCP settings from SQLite, initializing defaults if absent."""
    saved = storage.get_setting(MCP_SETTINGS_KEY, default=None)
    if not saved or not isinstance(saved, dict):
        saved = dict(DEFAULT_MCP_SETTINGS)
        storage.set_setting(MCP_SETTINGS_KEY, saved)
        return saved

    # Merge in any newly introduced default keys
    updated = False
    for k, v in DEFAULT_MCP_SETTINGS.items():
        if k not in saved:
            saved[k] = v
            updated = True
    if updated:
        storage.set_setting(MCP_SETTINGS_KEY, saved)
    return saved


def update_mcp_settings(storage: DiscoveryStorage, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Safely update and persist MCP configuration settings."""
    current = get_or_init_mcp_settings(storage)
    current.update(updates)
    storage.set_setting(MCP_SETTINGS_KEY, current)
    return current


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Check if a network port is actively bound and listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            return s.connect_ex((host, port)) == 0
        except Exception:
            return False


def ensure_dashboard_running(
    port: int = 8000,
    host: str = "127.0.0.1",
    open_browser: bool = True,
) -> Dict[str, Any]:
    """Check if the FastAPI dashboard is running, start it in background if not, and optionally open browser."""
    url = f"http://{host}:{port}"

    if importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("uvicorn") is None:
        return {
            "status": "unavailable",
            "message": 'The dashboard needs extra packages. Run: pip install "agent-reach[dashboard]".',
        }

    if is_port_in_use(port, host):
        if open_browser:
            webbrowser.open(url)
        return {"status": "already_running", "url": url, "port": port}

    # Start FastAPI dashboard as detached background subprocess
    flags = 0
    if sys.platform == "win32":
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)

    subprocess.Popen(
        [sys.executable, "-m", "agent_reach.cli", "dashboard", "--port", str(port), "--host", host],
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Poll up to 3 seconds for port to open
    started = False
    for _ in range(30):
        time.sleep(0.1)
        if is_port_in_use(port, host):
            started = True
            break

    if open_browser:
        webbrowser.open(url)

    return {
        "status": "started" if started else "starting",
        "url": url,
        "port": port,
    }
