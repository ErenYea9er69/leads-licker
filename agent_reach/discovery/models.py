# -*- coding: utf-8 -*-
"""Data models for AI Customer Discovery and Lead Generation."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class FactItem(BaseModel):
    """A verified fact extracted directly from the business website."""
    claim: str
    source_url: str
    category: str = "product"  # e.g., "pricing", "feature", "icp", "company"


class InferenceItem(BaseModel):
    """An AI-derived inference with an explicit confidence level."""
    insight: str
    confidence: float = Field(ge=0.0, le=1.0)
    basis: str


class BusinessProfile(BaseModel):
    """Structured understanding of the user's business."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    url: Optional[str] = None
    description: str = ""
    industry: str = ""
    niche: str = ""
    main_product_or_service: str = ""
    features: List[str] = Field(default_factory=list)
    problems_solved: List[str] = Field(default_factory=list)
    customer_outcomes: List[str] = Field(default_factory=list)
    icp: str = ""
    target_industries: List[str] = Field(default_factory=list)
    target_roles: List[str] = Field(default_factory=list)
    customer_demographics: List[str] = Field(default_factory=list)
    customer_frustrations: List[str] = Field(default_factory=list)
    competitors_and_alternatives: List[str] = Field(default_factory=list)
    unique_selling_points: List[str] = Field(default_factory=list)
    pricing_info: Optional[str] = None
    geographic_market: str = "Global"
    trigger_events: List[str] = Field(default_factory=list)
    # Phrases customers type when they have the problem. Search and scoring use them.
    pain_vocabulary: List[str] = Field(default_factory=list)
    # Kinds of people who must not become leads.
    not_for: List[str] = Field(default_factory=list)
    facts: List[FactItem] = Field(default_factory=list)
    inferences: List[InferenceItem] = Field(default_factory=list)
    confirmed: bool = False
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)


class SearchQuery(BaseModel):
    """A planned customer discovery search query."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    query: str
    intent_type: str = "frustration"  # frustration, alternative, recommendation, cost, tool_request
    platform: str = "reddit"  # reddit, hackernews, web, github, twitter, quora, youtube
    target_community: Optional[str] = None  # e.g. "r/startups"
    rationale: str = ""
    # Buyer stage: switching, solution, problem, category. Empty for old rows.
    stage: str = ""


class DiscoveredItem(BaseModel):
    """Raw conversation or post discovered from a community."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    url: str
    platform: str
    community: str = ""
    author: str = ""
    published_at: str = ""
    title: str = ""
    content: str = ""
    raw_data: Dict[str, Any] = Field(default_factory=dict)
    # Reply opportunity facts from thread_check: comments, age, commentable, warnings.
    thread_health: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)


class ScoreBreakdown(BaseModel):
    """Explainable 100-point score breakdown."""
    icp_match: int = Field(ge=0, le=25)
    problem_fit: int = Field(ge=0, le=30)
    buying_intent: int = Field(ge=0, le=20)
    urgency: int = Field(ge=0, le=15)
    recency: int = Field(ge=0, le=10)
    total: int = Field(ge=0, le=100)
    explanation: str = ""


LeadClassification = Literal[
    "high_potential",
    "relevant_potential",
    "customer_insight",
    "competitor_intel",
    "irrelevant",
]


class LeadQualification(BaseModel):
    """Qualified lead intelligence with supporting evidence and scoring."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    discovered_item_id: str
    title: str
    url: str
    platform: str
    community: str
    author: str
    published_at: str
    excerpt: str
    customer_problem: str
    pain_point_category: str
    profile_match: str
    competitor_mentioned: Optional[str] = None
    purchase_intent: Literal["High", "Medium", "Low", "None"] = "Medium"
    urgency: Literal["High", "Medium", "Low"] = "Medium"
    product_fit_explanation: str
    evidence: str
    score: int = Field(ge=0, le=100)
    score_breakdown: ScoreBreakdown
    classification: LeadClassification = "relevant_potential"
    confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    # "llm" when a model judged the thread, "heuristic" when only keyword rules ran.
    judged_by: Literal["llm", "heuristic"] = "heuristic"
    thread_health: Dict[str, Any] = Field(default_factory=dict)
    # Extra judgement data. All optional so old rows still load.
    post_type: str = ""
    evidence_verified: bool = False
    # "draft" means a reply may be drafted. "human_only" means the platform bans generated text.
    reply_policy: str = "draft"
    status: Literal["new", "rejected", "replied", "closed"] = "new"
    reject_reason: str = ""
    created_at: float = Field(default_factory=time.time)


class ReplyTarget(BaseModel):
    """Where inside a thread a reply goes: the post or one comment."""
    target_kind: Literal["post", "comment"] = "post"
    target_comment_id: str = ""
    target_author: str = ""
    target_text: str = ""
    reason: str = ""
    score: float = 0.0
    depth: int = 0
    age_hours: Optional[float] = None
    # Facts from the page the target sits on, such as the transcript excerpt of a video. Context only.
    context: str = ""


class GeneratedReply(BaseModel):
    """Value-first and product-aware response for a qualified lead."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    lead_id: str
    value_first: str
    product_aware: str = ""
    edited_reply: Optional[str] = None
    selected_version: Literal["value_first", "product_aware", "custom"] = "value_first"
    status: Literal["draft", "approved", "pending_manual_post", "published", "rejected"] = "draft"
    published_at: Optional[float] = None
    platform: str = "reddit"
    target_url: str = ""
    affiliation_disclosure: str = "Disclosure: I am associated with this product."
    error_message: Optional[str] = None
    # Reply target inside the thread.
    target_kind: Literal["post", "comment"] = "post"
    target_comment_id: str = ""
    target_author: str = ""
    target_text: str = ""
    target_reason: str = ""
    # Highest pitch level used by product_aware (0 to 3).
    pitch_level: int = 2
    # Lint reports per version, filled by the generator or the MCP gate.
    lint: Dict[str, Any] = Field(default_factory=dict)
    needs_human_edit: bool = False
    generated_by: str = "llm"
    # The linked account that owns this reply ("platform:handle"). Empty for drafts made before accounts existed.
    account_id: str = ""
    # Filled after posting.
    published_comment_id: str = ""
    published_url: str = ""
    outcome: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    @property
    def target_key(self) -> str:
        """"post" or "comment:<id>". One thread target takes one reply, ever."""
        if self.target_kind == "comment" and self.target_comment_id:
            return f"comment:{self.target_comment_id}"
        return "post"


class ReplyPreferences(BaseModel):
    """What the owner wants: voice, limits and pitch level. Stored once, used for every draft."""
    voice_samples: List[str] = Field(default_factory=list)
    voice_card: Dict[str, Any] = Field(default_factory=dict)
    banned_words: List[str] = Field(default_factory=list)
    use_user_banned_list: bool = True
    strict_avoid: bool = False
    avoid_budget: int = 2
    persona: Literal["founder", "employee", "maker", "contributor"] = "founder"
    pitch_level: int = Field(default=2, ge=0, le=3)
    language: str = "en"
    min_words: int = 15
    max_words: int = 120
    allow_links: bool = False
    allow_emoji: Optional[bool] = None
    updated_at: float = Field(default_factory=time.time)


class LinkedAccount(BaseModel):
    """An existing account the owner links. No password or cookie is stored here."""
    platform: str
    handle: str
    mode: Literal["manual", "api"] = "manual"
    # Short name used in credential variable names, such as REDDIT_ALT1_CLIENT_ID. Built from the handle when empty.
    alias: str = ""
    # Communities this account is best for. The app prefers it there. Empty means any.
    focus: List[str] = Field(default_factory=list)
    snapshot: Dict[str, Any] = Field(default_factory=dict)
    snapshot_at: Optional[float] = None
    voice_imported_at: Optional[float] = None
    added_at: float = Field(default_factory=time.time)


class CommunityRule(BaseModel):
    """What the owner read in a community's rules. The publisher uses it."""
    community: str
    self_promo: Literal["allowed", "thread_only", "banned", "unknown"] = "unknown"
    links_allowed: bool = False
    ai_content_allowed: bool = True
    min_karma: int = 0
    notes: str = ""
    acknowledged_at: float = Field(default_factory=time.time)


class PostingSettings(BaseModel):
    """Safety and control configuration for response publishing."""
    mode: Literal["draft", "manual", "automatic"] = "manual"
    daily_limit: int = 5
    min_interval_seconds: int = 600  # 10 minutes between posts
    # Empty means no whitelist. The community rules check still applies.
    allowed_communities: List[str] = Field(default_factory=list)
    # Product-aware replies need a linked account whose stored health allows the pitch level.
    require_account_health: bool = True
    emergency_stop: bool = False
    # Random extra wait on top of min_interval_seconds, as a fraction (0.3 means up to 30 percent).
    interval_jitter: float = 0.3
    # At most this share of recent comments may name the product.
    max_mention_ratio: float = 0.1
    # Block posts to a community until the owner records its rules.
    require_rules_ack: bool = True
    # One thread takes at most this many of the owner's replies, always from one account, never on the same target.
    max_replies_per_thread: int = Field(default=2, ge=1, le=3)
    # Minutes between two replies in the same thread.
    min_thread_gap_minutes: int = Field(default=60, ge=0)
    # Days during which only one of the owner's accounts may name the product in one community. 0 turns it off.
    product_community_gap_days: int = Field(default=7, ge=0, le=60)
    reddit_client_id: Optional[str] = None
    reddit_client_secret: Optional[str] = None
    reddit_username: Optional[str] = None
    reddit_password: Optional[str] = None
    github_token: Optional[str] = None


class Campaign(BaseModel):
    """A customer discovery campaign."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Default Campaign"
    business_profile_id: str = ""
    status: Literal["idle", "running", "completed", "failed", "cancelled"] = "idle"
    selected_platforms: List[str] = Field(default_factory=lambda: ["reddit", "hackernews", "web"])
    queries: List[SearchQuery] = Field(default_factory=list)
    # Why threads were dropped, e.g. {"archived": 12, "not_discussion": 7}.
    diagnostics: Dict[str, int] = Field(default_factory=dict)
    total_found: int = 0
    total_qualified: int = 0
    high_potential_count: int = 0
    progress_percentage: int = 0
    current_step: str = ""
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
