# -*- coding: utf-8 -*-
"""SQLite persistence layer for AI Customer Discovery & Lead Generation."""

from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from agent_reach.discovery.models import (
    BusinessProfile,
    Campaign,
    CommunityRule,
    DiscoveredItem,
    GeneratedReply,
    LeadQualification,
    PostingSettings,
)
from agent_reach.discovery.thread_check import canonical_url

# Optional. AGENT_REACH_DB_SYNC=NORMAL trades durability after a power cut for faster writes.
_SYNC_MODE = (os.getenv("AGENT_REACH_DB_SYNC") or "").strip().upper()
if _SYNC_MODE not in ("NORMAL", "OFF", "EXTRA"):
    _SYNC_MODE = ""

_SECRET_FIELDS = {"reddit_client_id", "reddit_client_secret", "reddit_username", "reddit_password", "github_token"}

DEFAULT_DB_PATH = Path(
    os.getenv("AGENT_REACH_DISCOVERY_DB")
    or (Path.home() / ".agent-reach" / "discovery.db")
)



# One idle connection per database file. SQLite checkpoints and deletes the WAL file whenever the
# last connection closes. Every storage call opens and closes its own connection, so without an
# idle one each call paid for a checkpoint. The idle connection runs no query after it opens.
_ANCHOR_LIMIT = 8
_anchors: "OrderedDict[str, tuple]" = OrderedDict()   # path -> (connection, inode, pid)
_anchor_lock = threading.Lock()


def _hold_anchor(db_path: Path) -> None:
    key = str(db_path)
    try:
        inode = os.stat(key).st_ino
    except OSError:
        return
    with _anchor_lock:
        held = _anchors.get(key)
        if held and held[1] == inode and held[2] == os.getpid():
            _anchors.move_to_end(key)
            return
        if held:
            _drop_anchor(key)
        try:
            conn = sqlite3.connect(key, timeout=30, check_same_thread=False)
            conn.execute("SELECT 1").fetchall()
        except sqlite3.Error:
            return
        _anchors[key] = (conn, inode, os.getpid())
        while len(_anchors) > _ANCHOR_LIMIT:
            _drop_anchor(next(iter(_anchors)))


def _drop_anchor(key: str) -> None:
    held = _anchors.pop(key, None)
    if held and held[2] == os.getpid():   # a forked child never closes its parent's handle
        try:
            held[0].close()
        except sqlite3.Error:
            pass


class DiscoveryStorage:
    """Manages SQLite storage for profiles, campaigns, leads, replies, and logs."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        if _SYNC_MODE:
            conn.execute(f"PRAGMA synchronous = {_SYNC_MODE}")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            # WAL lets the campaign thread write while the API reads.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS business_profiles (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    url TEXT,
                    confirmed INTEGER DEFAULT 0,
                    data JSON,
                    created_at REAL,
                    updated_at REAL
                );

                CREATE TABLE IF NOT EXISTS campaigns (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    business_profile_id TEXT,
                    status TEXT,
                    data JSON,
                    created_at REAL,
                    completed_at REAL
                );

                CREATE TABLE IF NOT EXISTS discovered_items (
                    id TEXT PRIMARY KEY,
                    url TEXT UNIQUE,
                    platform TEXT,
                    community TEXT,
                    author TEXT,
                    title TEXT,
                    content TEXT,
                    data JSON,
                    created_at REAL
                );

                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    discovered_item_id TEXT,
                    campaign_id TEXT,
                    url TEXT,
                    platform TEXT,
                    community TEXT,
                    title TEXT,
                    customer_problem TEXT,
                    pain_point_category TEXT,
                    buying_intent TEXT,
                    urgency TEXT,
                    score INTEGER,
                    classification TEXT,
                    confidence REAL,
                    data JSON,
                    created_at REAL
                );

                CREATE TABLE IF NOT EXISTS replies (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT,
                    target_key TEXT NOT NULL DEFAULT 'post',
                    status TEXT,
                    selected_version TEXT,
                    data JSON,
                    created_at REAL,
                    updated_at REAL,
                    UNIQUE (lead_id, target_key)
                );

                CREATE TABLE IF NOT EXISTS posting_logs (
                    id TEXT PRIMARY KEY,
                    lead_id TEXT,
                    reply_id TEXT,
                    platform TEXT,
                    target_url TEXT,
                    content TEXT,
                    mode TEXT,
                    status TEXT,
                    error_message TEXT,
                    created_at REAL,
                    account_id TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value JSON,
                    updated_at REAL
                );

                CREATE INDEX IF NOT EXISTS idx_leads_score ON leads (score DESC);
                CREATE INDEX IF NOT EXISTS idx_leads_classification ON leads (classification);
                CREATE INDEX IF NOT EXISTS idx_discovered_url ON discovered_items (url);
                """
            )

        _hold_anchor(self.db_path)
        self._migrate()

        # The settings table holds API keys. Keep the file private to this user.
        try:
            os.chmod(self.db_path, 0o600)
        except OSError:
            pass

    def close(self) -> None:
        """Release the idle connection for this database. Later calls still work and open a new one."""
        with _anchor_lock:
            _drop_anchor(str(self.db_path))

    def _migrate(self) -> None:
        """Add columns that older databases lack. Safe to run on every start."""
        with self._connection() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(posting_logs)").fetchall()}
            if "kind" not in cols:
                conn.execute("ALTER TABLE posting_logs ADD COLUMN kind TEXT DEFAULT ''")
            if "account_id" not in cols:
                conn.execute("ALTER TABLE posting_logs ADD COLUMN account_id TEXT DEFAULT ''")
            self._migrate_replies(conn)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posting_account ON posting_logs (account_id, platform, status, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_replies_lead ON replies (lead_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_posting_platform ON posting_logs (platform, status, created_at)")
            # Newest-first lists read the index and stop at the limit. Without these, each list scanned the whole table.
            conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_created ON discovered_items (created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_discovered_platform_created ON discovered_items (platform, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_replies_created ON replies (created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_profiles_updated ON business_profiles (updated_at)")
        self._scrub_stored_secrets()

    @staticmethod
    def _migrate_replies(conn: sqlite3.Connection) -> None:
        """Older databases allowed one reply per lead. A thread now takes up to three, one per target."""
        if "target_key" in {r["name"] for r in conn.execute("PRAGMA table_info(replies)").fetchall()}:
            return
        conn.execute("BEGIN IMMEDIATE")
        if "target_key" in {r["name"] for r in conn.execute("PRAGMA table_info(replies)").fetchall()}:
            return   # another process finished the migration first
        old = conn.execute("SELECT id, lead_id, status, selected_version, data, created_at, updated_at FROM replies").fetchall()
        conn.execute("ALTER TABLE replies RENAME TO replies_old")
        conn.execute(
            """CREATE TABLE replies (
                id TEXT PRIMARY KEY, lead_id TEXT, target_key TEXT NOT NULL DEFAULT 'post', status TEXT,
                selected_version TEXT, data JSON, created_at REAL, updated_at REAL, UNIQUE (lead_id, target_key))"""
        )
        for row in old:
            try:
                data = json.loads(row["data"])
            except (TypeError, ValueError):
                data = {}
            key = f"comment:{data['target_comment_id']}" if data.get("target_kind") == "comment" and data.get("target_comment_id") else "post"
            conn.execute(
                "INSERT INTO replies (id, lead_id, target_key, status, selected_version, data, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
                (row["id"], row["lead_id"], key, row["status"], row["selected_version"], row["data"], row["created_at"], row["updated_at"]),
            )
        conn.execute("DROP TABLE replies_old")

    def _scrub_stored_secrets(self) -> None:
        """Older versions of the dashboard saved Reddit and GitHub credentials in the database. Remove them."""
        raw = self.get_setting("posting_settings", None)
        if isinstance(raw, dict) and any(raw.get(k) for k in _SECRET_FIELDS):
            self.set_setting("posting_settings", {k: v for k, v in raw.items() if k not in _SECRET_FIELDS})

    # ── Business Profiles ──

    def save_business_profile(self, profile: BusinessProfile) -> None:
        profile.updated_at = time.time()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO business_profiles (id, name, url, confirmed, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    url=excluded.url,
                    confirmed=excluded.confirmed,
                    data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (
                    profile.id,
                    profile.name,
                    profile.url or "",
                    1 if profile.confirmed else 0,
                    profile.model_dump_json(),
                    profile.created_at,
                    profile.updated_at,
                ),
            )

    def get_business_profile(self, profile_id: str) -> Optional[BusinessProfile]:
        with self._connection() as conn:
            row = conn.execute("SELECT data FROM business_profiles WHERE id = ?", (profile_id,)).fetchone()
            if row:
                return BusinessProfile.model_validate_json(row["data"])
        return None

    def get_latest_business_profile(self) -> Optional[BusinessProfile]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT data FROM business_profiles ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            if row:
                return BusinessProfile.model_validate_json(row["data"])
        return None

    # ── Campaigns ──

    def save_campaign(self, campaign: Campaign) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO campaigns (id, name, business_profile_id, status, data, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    status=excluded.status,
                    data=excluded.data,
                    completed_at=excluded.completed_at
                """,
                (
                    campaign.id,
                    campaign.name,
                    campaign.business_profile_id,
                    campaign.status,
                    campaign.model_dump_json(),
                    campaign.created_at,
                    campaign.completed_at,
                ),
            )

    def get_campaign(self, campaign_id: str) -> Optional[Campaign]:
        with self._connection() as conn:
            row = conn.execute("SELECT data FROM campaigns WHERE id = ?", (campaign_id,)).fetchone()
            if row:
                return Campaign.model_validate_json(row["data"])
        return None

    def mark_stale_campaigns_failed(self) -> int:
        """A restart kills background threads. Close campaigns left in 'running'."""
        stale = [c for c in self.list_campaigns(limit=200) if c.status == "running"]
        for campaign in stale:
            campaign.status = "failed"
            campaign.current_step = "Interrupted by a server restart. Launch the campaign again."
            self.save_campaign(campaign)
        return len(stale)

    def list_campaigns(self, limit: int = 50) -> List[Campaign]:
        with self._connection() as conn:
            rows = conn.execute("SELECT data FROM campaigns ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            return [Campaign.model_validate_json(r["data"]) for r in rows]

    # ── Discovered Items & Deduplication ──

    def save_discovered_item(self, item: DiscoveredItem) -> bool:
        """Saves item. Returns True if inserted, False if duplicate."""
        item.url = canonical_url(item.url)
        try:
            with self._connection() as conn:
                conn.execute(
                    """
                    INSERT INTO discovered_items (id, url, platform, community, author, title, content, data, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.id,
                        item.url,
                        item.platform,
                        item.community,
                        item.author,
                        item.title,
                        item.content,
                        item.model_dump_json(),
                        item.created_at,
                    ),
                )
                return True
        except sqlite3.IntegrityError:
            # A thread the intake search found early waits for the scout. The scout's own harvest claims it once.
            return self._claim_prefetched(item)

    def _claim_prefetched(self, item: DiscoveredItem) -> bool:
        with self._connection() as conn:
            row = conn.execute("SELECT id, data FROM discovered_items WHERE url = ?", (item.url,)).fetchone()
            if row is None:
                return False
            try:
                held = json.loads(row["data"])
            except ValueError:
                return False
            if not (held.get("raw_data") or {}).get("prefetch"):
                return False
            conn.execute(
                "UPDATE discovered_items SET id=?, platform=?, community=?, author=?, title=?, content=?, data=?, created_at=? WHERE id=?",
                (item.id, item.platform, item.community, item.author, item.title, item.content,
                 item.model_dump_json(), item.created_at, row["id"]),
            )
            return True

    def get_discovered_item(self, item_id: str) -> Optional[DiscoveredItem]:
        with self._connection() as conn:
            row = conn.execute("SELECT data FROM discovered_items WHERE id = ?", (item_id,)).fetchone()
            return DiscoveredItem.model_validate_json(row["data"]) if row else None

    def get_discovered_item_by_url(self, url: str) -> Optional[DiscoveredItem]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT data FROM discovered_items WHERE url = ? OR url = ?", (canonical_url(url), url)
            ).fetchone()
            return DiscoveredItem.model_validate_json(row["data"]) if row else None

    def list_discovered_items(self, limit: int = 50, platform: Optional[str] = None) -> List[DiscoveredItem]:
        """Newest harvested threads first."""
        query = "SELECT data FROM discovered_items"
        params: List[Any] = []
        if platform:
            query += " WHERE platform = ?"
            params.append(platform)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connection() as conn:
            rows = conn.execute(query, params).fetchall()
        return [DiscoveredItem.model_validate_json(r["data"]) for r in rows]

    def update_discovered_item(self, item: DiscoveredItem) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE discovered_items SET data = ? WHERE id = ?", (item.model_dump_json(), item.id))

    def is_url_discovered(self, url: str) -> bool:
        """True when the thread is stored and already handed on. A prefetched thread nobody claimed yet counts as new."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT data FROM discovered_items WHERE url = ? OR url = ?", (canonical_url(url), url)
            ).fetchone()
        if row is None:
            return False
        try:
            return not (json.loads(row["data"]).get("raw_data") or {}).get("prefetch")
        except ValueError:
            return True

    def mark_prefetched(self, item_id: str) -> None:
        """Flag a stored thread as found ahead of the scout. The scout's harvest claims it later."""
        item = self.get_discovered_item(item_id)
        if item is not None:
            item.raw_data = {**(item.raw_data or {}), "prefetch": True}
            self.update_discovered_item(item)

    def count_prefetched(self) -> int:
        with self._connection() as conn:
            rows = conn.execute("SELECT data FROM discovered_items ORDER BY created_at DESC LIMIT 500").fetchall()
        return sum(1 for r in rows if (json.loads(r["data"]).get("raw_data") or {}).get("prefetch"))

    # ── Leads ──

    def save_lead(self, lead: LeadQualification, campaign_id: str = "") -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO leads (
                    id, discovered_item_id, campaign_id, url, platform, community,
                    title, customer_problem, pain_point_category, buying_intent, urgency,
                    score, classification, confidence, data, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    score=excluded.score,
                    classification=excluded.classification,
                    confidence=excluded.confidence,
                    data=excluded.data
                """,
                (
                    lead.id,
                    lead.discovered_item_id,
                    campaign_id,
                    lead.url,
                    lead.platform,
                    lead.community,
                    lead.title,
                    lead.customer_problem,
                    lead.pain_point_category,
                    lead.purchase_intent,
                    lead.urgency,
                    lead.score,
                    lead.classification,
                    lead.confidence,
                    lead.model_dump_json(),
                    lead.created_at,
                ),
            )

    def get_lead(self, lead_id: str) -> Optional[LeadQualification]:
        with self._connection() as conn:
            row = conn.execute("SELECT data FROM leads WHERE id = ?", (lead_id,)).fetchone()
            if row:
                return LeadQualification.model_validate_json(row["data"])
        return None

    def get_lead_by_url(self, url: str) -> Optional[LeadQualification]:
        canon = canonical_url(url)
        with self._connection() as conn:
            row = conn.execute(
                "SELECT data FROM leads WHERE url = ? OR url = ?", (canon, url)
            ).fetchone()
            if row:
                return LeadQualification.model_validate_json(row["data"])
            item = self.get_discovered_item_by_url(url)
            if item:
                lead_row = conn.execute(
                    "SELECT data FROM leads WHERE discovered_item_id = ?", (item.id,)
                ).fetchone()
                if lead_row:
                    return LeadQualification.model_validate_json(lead_row["data"])
        return None

    def list_leads(
        self,
        min_score: int = 0,
        platform: Optional[str] = None,
        classification: Optional[str] = None,
        pain_point_category: Optional[str] = None,
        buying_intent: Optional[str] = None,
        query: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        include_rejected: bool = False,
    ) -> List[LeadQualification]:
        conditions = ["score >= ?"]
        params: List[Any] = [min_score]
        if not include_rejected:
            conditions.append("COALESCE(json_extract(data, '$.status'), 'new') != 'rejected'")

        if platform:
            conditions.append("platform = ?")
            params.append(platform)
        if classification:
            conditions.append("classification = ?")
            params.append(classification)
        if pain_point_category:
            conditions.append("pain_point_category = ?")
            params.append(pain_point_category)
        if buying_intent:
            conditions.append("buying_intent = ?")
            params.append(buying_intent)
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            conditions.append("(title LIKE ? ESCAPE '\\' OR customer_problem LIKE ? ESCAPE '\\')")
            params.extend([f"%{escaped}%", f"%{escaped}%"])

        limit = max(1, min(int(limit), 500))
        offset = max(0, int(offset))
        params.extend([limit, offset])
        sql = f"""
            SELECT data FROM leads
            WHERE {' AND '.join(conditions)}
            ORDER BY score DESC, created_at DESC
            LIMIT ? OFFSET ?
        """
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [LeadQualification.model_validate_json(r["data"]) for r in rows]

    def set_lead_status(self, lead_id: str, status: str, reason: str = "") -> Optional[LeadQualification]:
        lead = self.get_lead(lead_id)
        if not lead:
            return None
        lead.status = status  # type: ignore[assignment]
        lead.reject_reason = reason
        self.save_lead(lead)
        return lead

    def count_leads(self) -> Dict[str, int]:
        with self._connection() as conn:
            total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
            high_potential = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE classification = 'high_potential'"
            ).fetchone()[0]
            relevant = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE classification = 'relevant_potential'"
            ).fetchone()[0]
            insights = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE classification = 'customer_insight'"
            ).fetchone()[0]
            competitors = conn.execute(
                "SELECT COUNT(*) FROM leads WHERE classification = 'competitor_intel'"
            ).fetchone()[0]
            return {
                "total": total,
                "high_potential": high_potential,
                "relevant": relevant,
                "customer_insights": insights,
                "competitor_intel": competitors,
            }

    # ── Replies ──

    def save_reply(self, reply: GeneratedReply, keep_others: bool = False) -> None:
        """Save a reply. A thread target takes one reply, so a new draft for the same target replaces the old one.

        A draft for a different target replaces the lead's open draft, unless `keep_others` is set or the
        earlier replies are already approved or posted. Then it becomes a second reply on the thread.
        """
        reply.updated_at = time.time()
        key = reply.target_key
        with self._connection() as conn:
            same = conn.execute(
                "SELECT id, created_at FROM replies WHERE lead_id = ? AND target_key = ?", (reply.lead_id, key)
            ).fetchone()
            if same and same["id"] != reply.id:
                reply.id, reply.created_at = same["id"], same["created_at"]
            elif not same and not keep_others:
                draft = conn.execute(
                    "SELECT id, created_at FROM replies WHERE lead_id = ? AND status = 'draft' AND id != ? "
                    "ORDER BY updated_at DESC LIMIT 1", (reply.lead_id, reply.id),
                ).fetchone()
                if draft:
                    reply.id, reply.created_at = draft["id"], draft["created_at"]
            conn.execute(
                """
                INSERT INTO replies (id, lead_id, target_key, status, selected_version, data, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    target_key=excluded.target_key,
                    status=excluded.status,
                    selected_version=excluded.selected_version,
                    data=excluded.data,
                    updated_at=excluded.updated_at
                """,
                (
                    reply.id, reply.lead_id, key, reply.status, reply.selected_version,
                    reply.model_dump_json(), reply.created_at, reply.updated_at,
                ),
            )

    def get_reply(self, reply_id: str) -> Optional[GeneratedReply]:
        with self._connection() as conn:
            row = conn.execute("SELECT data FROM replies WHERE id = ?", (reply_id,)).fetchone()
            return GeneratedReply.model_validate_json(row["data"]) if row else None

    def get_reply_by_lead_id(self, lead_id: str) -> Optional[GeneratedReply]:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT data FROM replies WHERE lead_id = ? ORDER BY updated_at DESC LIMIT 1", (lead_id,)
            ).fetchone()
            if row:
                return GeneratedReply.model_validate_json(row["data"])
        return None

    def list_replies_for_lead(self, lead_id: str) -> List[GeneratedReply]:
        with self._connection() as conn:
            rows = conn.execute("SELECT data FROM replies WHERE lead_id = ? ORDER BY created_at", (lead_id,)).fetchall()
            return [GeneratedReply.model_validate_json(r["data"]) for r in rows]

    def thread_replies(self, url: str) -> List[GeneratedReply]:
        """Every live reply (not rejected) on one thread, from any lead and any account."""
        from agent_reach.discovery.thread_check import canonical_url

        urls = list({url, canonical_url(url)})
        marks = ",".join("?" for _ in urls)
        with self._connection() as conn:
            rows = conn.execute(
                f"SELECT r.data FROM replies r JOIN leads l ON l.id = r.lead_id "
                f"WHERE l.url IN ({marks}) AND r.status != 'rejected' ORDER BY r.created_at", urls,
            ).fetchall()
            return [GeneratedReply.model_validate_json(r["data"]) for r in rows]

    def list_replies(self, status: Optional[str] = None, limit: int = 100) -> List[GeneratedReply]:
        with self._connection() as conn:
            if status:
                rows = conn.execute(
                    "SELECT data FROM replies WHERE status = ? ORDER BY updated_at DESC LIMIT ?",
                    (status, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT data FROM replies ORDER BY updated_at DESC LIMIT ?", (limit,)
                ).fetchall()
            return [GeneratedReply.model_validate_json(r["data"]) for r in rows]

    # ── Posting Logs ──

    def log_post(
        self,
        lead_id: str,
        reply_id: str,
        platform: str,
        target_url: str,
        content: str,
        mode: str,
        status: str,
        error_message: Optional[str] = None,
        kind: str = "",
        account_id: str = "",
    ) -> None:
        import uuid

        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO posting_logs (
                    id, lead_id, reply_id, platform, target_url, content, mode, status, error_message, created_at, kind,
                    account_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    lead_id,
                    reply_id,
                    platform,
                    target_url,
                    content,
                    mode,
                    status,
                    error_message or "",
                    time.time(),
                    kind,
                    account_id,
                ),
            )

    def recent_published_kinds(
        self, platform: Optional[str] = None, limit: int = 30, since_days: int = 30, account_id: Optional[str] = None
    ) -> List[str]:
        """Kinds ("value_first" or "product_aware") of the latest published replies, newest first."""
        cutoff = time.time() - since_days * 86400
        sql = "SELECT kind FROM posting_logs WHERE status = 'published' AND created_at >= ?"
        params: List[Any] = [cutoff]
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        if account_id:
            sql += " AND account_id = ?"
            params.append(account_id)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connection() as conn:
            return [r["kind"] or "" for r in conn.execute(sql, params).fetchall()]

    def product_posters(self, platform: str, community: str, days: int) -> List[str]:
        """Accounts that named the product in one community during the last `days` days."""
        if not community or days <= 0:
            return []
        sql = (
            "SELECT DISTINCT p.account_id FROM posting_logs p JOIN leads l ON l.id = p.lead_id "
            "WHERE p.platform = ? AND lower(l.community) = ? AND p.kind = 'product_aware' "
            "AND p.status IN ('published', 'pending_manual_post') AND p.created_at >= ?"
        )
        with self._connection() as conn:
            rows = conn.execute(sql, (platform, community.lower(), time.time() - days * 86400)).fetchall()
        return [r["account_id"] or "" for r in rows]

    def list_posting_logs(self, limit: int = 50, platform: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM posting_logs"
        params: List[Any] = []
        if platform:
            sql += " WHERE platform = ?"
            params.append(platform)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connection() as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def last_published_at(self, platform: Optional[str] = None, account_id: Optional[str] = None) -> Optional[float]:
        sql = "SELECT MAX(created_at) FROM posting_logs WHERE status = 'published'"
        params: List[Any] = []
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        if account_id:
            sql += " AND account_id = ?"
            params.append(account_id)
        with self._connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return row[0] if row and row[0] else None

    def count_posts_today(self, platform: Optional[str] = None, account_id: Optional[str] = None) -> int:
        sql = "SELECT COUNT(*) FROM posting_logs WHERE status = 'published' AND created_at >= ?"
        params: List[Any] = [time.time() - (time.time() % 86400)]
        if platform:
            sql += " AND platform = ?"
            params.append(platform)
        if account_id:
            sql += " AND account_id = ?"
            params.append(account_id)
        with self._connection() as conn:
            row = conn.execute(sql, params).fetchone()
            return row[0] if row else 0

    # ── Settings ──

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if row:
                raw = row["value"]
                # The column type has numeric affinity, so a stored number comes back as a number, not as text.
                return json.loads(raw) if isinstance(raw, (str, bytes)) else raw
        return default

    def set_setting(self, key: str, value: Any) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, json.dumps(value), time.time()),
            )

    # Community rules the owner read. The publisher checks them before every post.

    @staticmethod
    def _rule_key(community: str) -> str:
        return (community or "").strip().lower().removeprefix("r/")

    def list_community_rules(self) -> List[CommunityRule]:
        raw = self.get_setting("community_rules", {}) or {}
        out: List[CommunityRule] = []
        for item in raw.values():
            try:
                out.append(CommunityRule.model_validate(item))
            except Exception:
                continue
        return out

    def get_community_rule(self, community: str) -> Optional[CommunityRule]:
        raw = (self.get_setting("community_rules", {}) or {}).get(self._rule_key(community))
        if not raw:
            return None
        try:
            return CommunityRule.model_validate(raw)
        except Exception:
            return None

    def save_community_rule(self, rule: CommunityRule) -> None:
        raw = self.get_setting("community_rules", {}) or {}
        raw[self._rule_key(rule.community)] = rule.model_dump()
        self.set_setting("community_rules", raw)

    def has_published_url(self, url: str) -> bool:
        """True when a reply already went out (or waits to go out) on this thread."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT 1 FROM posting_logs WHERE target_url = ? AND status IN ('published', 'pending_manual_post') LIMIT 1",
                (url,),
            ).fetchone()
        return row is not None

    def get_posting_settings(self) -> PostingSettings:
        raw = self.get_setting("posting_settings", {}) or {}
        try:
            return PostingSettings.model_validate(raw)
        except Exception:
            return PostingSettings()

    def save_posting_settings(self, settings: PostingSettings) -> None:
        # Passwords and tokens are never written to the database. Read them from the environment.
        self.set_setting("posting_settings", settings.model_dump(exclude=_SECRET_FIELDS))

    # ── Exporting (CSV / JSON) ──

    def export_leads_json(self, min_score: int = 0) -> str:
        leads = self.list_leads(min_score=min_score, limit=1000)
        return json.dumps([lead.model_dump() for lead in leads], indent=2)

    def export_leads_csv(self, min_score: int = 0) -> str:
        leads = self.list_leads(min_score=min_score, limit=1000)
        output = io.StringIO()
        writer = csv.writer(output)

        def safe(value: Any) -> Any:
            # Titles and excerpts come from the internet. A leading = + - @ makes
            # Excel run the cell as a formula, so prefix a quote.
            text = "" if value is None else str(value)
            return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else value

        writer.writerow([
            "Lead ID",
            "Title",
            "Score",
            "Classification",
            "Platform",
            "Community",
            "Author",
            "Date",
            "URL",
            "Customer Problem",
            "Pain Point Category",
            "Buying Intent",
            "Urgency",
            "Evidence",
        ])
        for lead in leads:
            writer.writerow([safe(v) for v in (
                lead.id,
                lead.title,
                lead.score,
                lead.classification,
                lead.platform,
                lead.community,
                lead.author,
                lead.published_at,
                lead.url,
                lead.customer_problem,
                lead.pain_point_category,
                lead.purchase_intent,
                lead.urgency,
                lead.evidence,
            )])
        return output.getvalue()

    def backup(self, target_path: Path) -> Path:
        """Create an online atomic backup of the database, safe during concurrent writes."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as src_conn:
            dest_conn = sqlite3.connect(str(target_path))
            try:
                src_conn.backup(dest_conn)
            finally:
                dest_conn.close()
        return target_path
