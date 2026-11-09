import React, { useEffect, useState, useCallback } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Inbox,
  MessageSquare,
  Search,
  X,
  Lock,
  MessageCircle,
  Sparkles,
  Bot,
  AlertTriangle,
  ShieldAlert,
  Video,
} from 'lucide-react';
import type { LeadQualification } from '../types';
import { api } from '../api';

interface LeadsViewProps {
  leads: LeadQualification[];
  onOpenReplyStudio: (leadId: string) => void;
}

const PAGE_SIZE = 25;

const PLATFORM_LABELS: Record<string, string> = {
  reddit: 'Reddit',
  hackernews: 'Hacker News',
  web: 'Public Web',
  youtube: 'YouTube',
  quora: 'Quora',
  github: 'GitHub Issues',
  twitter: 'Twitter / X',
};

const scoreFilter = (value: string) =>
  value === 'high'
    ? { min_score: 75 }
    : value === 'relevant'
    ? { min_score: 50, classification: 'relevant_potential' }
    : value === 'insight'
    ? { classification: 'customer_insight' }
    : value === 'competitor'
    ? { classification: 'competitor_intel' }
    : {};

export const LeadsView: React.FC<LeadsViewProps> = ({ leads: initialLeads, onOpenReplyStudio }) => {
  const [leads, setLeads] = useState(initialLeads);
  const [filterScore, setFilterScore] = useState('all');
  const [filterPlatform, setFilterPlatform] = useState('all');
  const [filterIntent, setFilterIntent] = useState('all');
  const [filterCategory, setFilterCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(0);
  const [selectedLead, setSelectedLead] = useState<LeadQualification | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLeads = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listLeads({
        ...scoreFilter(filterScore),
        platform: filterPlatform === 'all' ? undefined : filterPlatform,
        buying_intent: filterIntent === 'all' ? undefined : filterIntent,
        pain_point_category: filterCategory === 'all' ? undefined : filterCategory,
        query: searchQuery.trim() || undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      setLeads(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load qualified leads.');
    } finally {
      setLoading(false);
    }
  }, [filterScore, filterPlatform, filterIntent, filterCategory, searchQuery, page]);

  useEffect(() => {
    void loadLeads();
  }, [loadLeads]);

  const resetPage = (setter: (value: string) => void, value: string) => {
    setter(value);
    setPage(0);
  };

  return (
    <div className="page-shell leads-page">
      <section className="page-heading">
        <div>
          <h1>Qualified Customer Discussions</h1>
          <p>
            Review customer evidence quotes, examine thread activity and reply opportunities, and prioritize high-value responses.
          </p>
        </div>
        <div className="queue-summary">
          <strong className="tabular">{loading ? '…' : leads.length}</strong>
          <span>opportunities visible</span>
        </div>
      </section>

      {/* Filter Toolbar */}
      <section className="filter-bar panel" style={{ flexWrap: 'wrap', gap: 'var(--sp-3)' }}>
        <div className="search-field">
          <Search size={16} />
          <input
            id="leads-search-input"
            aria-label="Search leads by problem, title, or community"
            className="input"
            placeholder="Search problems, pain keywords, subreddits…"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(0);
            }}
          />
        </div>

        <select
          aria-label="Filter by classification"
          className="select"
          value={filterScore}
          onChange={(e) => resetPage(setFilterScore, e.target.value)}
        >
          <option value="all">All Classifications</option>
          <option value="high">High Potential (75+)</option>
          <option value="relevant">Relevant Leads (50–74)</option>
          <option value="insight">Customer Insights</option>
          <option value="competitor">Competitor Intel</option>
        </select>

        <select
          aria-label="Filter by platform"
          className="select"
          value={filterPlatform}
          onChange={(e) => resetPage(setFilterPlatform, e.target.value)}
        >
          <option value="all">All Sources</option>
          <option value="reddit">Reddit</option>
          <option value="hackernews">Hacker News</option>
          <option value="web">Public Web</option>
          <option value="youtube">YouTube</option>
          <option value="quora">Quora</option>
          <option value="github">GitHub Issues</option>
          <option value="twitter">Twitter / X</option>
        </select>

        <select
          aria-label="Filter by intent"
          className="select"
          value={filterIntent}
          onChange={(e) => resetPage(setFilterIntent, e.target.value)}
        >
          <option value="all">All Intent Levels</option>
          <option value="High">High Buying Intent</option>
          <option value="Medium">Medium Intent</option>
          <option value="Low">Low Intent</option>
        </select>

        <select
          aria-label="Filter by pain category"
          className="select"
          value={filterCategory}
          onChange={(e) => resetPage(setFilterCategory, e.target.value)}
        >
          <option value="all">All Pain Categories</option>
          <option value="cost">Cost & Pricing</option>
          <option value="tool_request">Tool Recommendations</option>
          <option value="frustration">Frustrations & Venting</option>
          <option value="alternative">Competitor Alternatives</option>
          <option value="workflow">Workflow & Process</option>
          <option value="integration">Integrations & Setup</option>
        </select>
      </section>

      {error && (
        <div className="notice notice-error" role="alert">
          <span>{error}</span>
          <button className="btn btn-secondary btn-sm" onClick={() => void loadLeads()}>
            Retry loading
          </button>
        </div>
      )}

      {/* Leads Table Panel */}
      <section className="panel lead-table-panel">
        <div className="table-header">
          <div>
            <h2>Discovered Opportunities</h2>
            <span>Page {page + 1} · Ranked by pain alignment and buying intent</span>
          </div>
          <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-subtle)' }}>
            Select any item to inspect qualification scoring and thread health
          </span>
        </div>

        {loading ? (
          <div className="table-empty">Loading matching opportunities…</div>
        ) : leads.length === 0 ? (
          <div className="table-empty">
            <div className="empty-icon">
              <Inbox size={20} />
            </div>
            <strong>
              {searchQuery || filterScore !== 'all' || filterPlatform !== 'all' || filterIntent !== 'all' || filterCategory !== 'all'
                ? 'No leads match these filters'
                : 'Your discovery queue is empty'}
            </strong>
            <span>
              {searchQuery || filterScore !== 'all' || filterPlatform !== 'all' || filterIntent !== 'all' || filterCategory !== 'all'
                ? 'Try clearing search keywords or adjusting your classification and intent filters.'
                : 'Confirm your business profile and launch your first customer discovery campaign to uncover qualified buyer discussions.'}
            </span>
          </div>
        ) : (
          <div className="lead-list">
            {leads.map((lead) => {
              const th = lead.thread_health;
              const isLocked = th?.commentable === false;
              const isCrowded = th?.crowded === true;
              const isHN = lead.platform === 'hackernews';
              const isHumanOnly = lead.reply_policy === 'human_only' || isHN;

              return (
                <div
                  className="lead-row"
                  key={lead.id}
                  onClick={() => setSelectedLead(lead)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      setSelectedLead(lead);
                    }
                  }}
                >
                  <div
                    className={`score-badge ${
                      lead.score >= 75
                        ? 'score-badge-high'
                        : lead.score >= 50
                        ? 'score-badge-mid'
                        : 'score-badge-low'
                    }`}
                  >
                    <strong className="tabular">{lead.score}</strong>
                    <span>/100</span>
                  </div>

                  <div className="lead-main">
                    <div className="lead-meta" style={{ flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
                      {lead.platform === 'youtube' ? (
                        <span className="badge" style={{ background: '#fef2f2', color: '#991b1b', borderColor: '#fecaca' }}>
                          <Video size={11} style={{ display: 'inline', marginRight: '3px' }} />
                          YouTube
                        </span>
                      ) : (
                        <span className="badge badge-low">{PLATFORM_LABELS[lead.platform] || lead.platform}</span>
                      )}
                      <span style={{ fontWeight: 600 }}>{lead.community}</span>
                      <span>·</span>
                      <span>{lead.published_at || 'Recent'}</span>

                      {/* Judged By AI vs Heuristic */}
                      {lead.judged_by === 'llm' ? (
                        <span className="badge badge-high" title="Evaluated by AI LLM">
                          <Bot size={11} style={{ display: 'inline', marginRight: '3px' }} />
                          AI Judged
                        </span>
                      ) : (
                        <span className="badge badge-low" title="Matched via heuristic rules">
                          Rule Match
                        </span>
                      )}

                      {/* Thread Health badges */}
                      {isLocked && (
                        <span className="badge badge-danger" title="Thread is archived or locked against new comments">
                          <Lock size={11} style={{ display: 'inline', marginRight: '3px' }} />
                          Locked
                        </span>
                      )}

                      {isCrowded && (
                        <span className="badge badge-amber" title="80+ comments: new replies risk getting buried">
                          Crowded
                        </span>
                      )}

                      {isHumanOnly && (
                        <span className="badge badge-amber" title="Platform forbids AI generated comments">
                          Manual / Research
                        </span>
                      )}

                      {th?.num_comments !== undefined && th.num_comments !== null && (
                        <span
                          style={{
                            fontSize: 'var(--fs-2xs)',
                            color: 'var(--text-subtle)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '3px',
                          }}
                        >
                          <MessageCircle size={11} />
                          {th.num_comments}
                        </span>
                      )}

                      {lead.competitor_mentioned && (
                        <span className="badge badge-amber">vs {lead.competitor_mentioned}</span>
                      )}
                    </div>

                    <h3>{lead.title}</h3>
                    <p>
                      <strong>{lead.customer_problem}</strong>
                    </p>
                    <div className="evidence-line">&ldquo;{lead.excerpt}&rdquo;</div>
                  </div>

                  <div className="lead-side">
                    <span
                      className={`intent-pill ${lead.urgency === 'High' ? 'intent-pill-urgent' : ''}`}
                    >
                      {lead.purchase_intent} intent
                    </span>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenReplyStudio(lead.id);
                      }}
                    >
                      <MessageSquare size={13} />
                      <span>{isHumanOnly ? 'View thread' : 'Open reply'}</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="pagination">
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setPage((value) => Math.max(0, value - 1))}
            disabled={page === 0 || loading}
          >
            <ChevronLeft size={14} />
            <span>Previous</span>
          </button>
          <span style={{ fontWeight: 600, fontSize: 'var(--fs-xs)' }}>Page {page + 1}</span>
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setPage((value) => value + 1)}
            disabled={loading || leads.length < PAGE_SIZE}
          >
            <span>Next</span>
            <ChevronRight size={14} />
          </button>
        </div>
      </section>

      {/* Lead Detail Inspection Modal */}
      {selectedLead && (
        <div
          className="modal-backdrop"
          onClick={() => setSelectedLead(null)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="modal-lead-title"
        >
          <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <div className="lead-meta" style={{ flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
                  <span
                    className={`badge ${
                      selectedLead.score >= 75 ? 'badge-high' : 'badge-medium'
                    }`}
                  >
                    Score {selectedLead.score}/100
                  </span>
                  <span className="badge badge-low">
                    {selectedLead.classification.replaceAll('_', ' ')}
                  </span>
                  {selectedLead.judged_by === 'llm' ? (
                    <span className="badge badge-high">
                      <Sparkles size={11} style={{ display: 'inline', marginRight: '3px' }} />
                      AI Evaluated ({Math.round((selectedLead.confidence || 0.85) * 100)}% Confidence)
                    </span>
                  ) : (
                    <span className="badge badge-low">
                      Heuristic Rules Qualified
                    </span>
                  )}
                  {selectedLead.competitor_mentioned && (
                    <span className="badge badge-amber">Competitor: {selectedLead.competitor_mentioned}</span>
                  )}
                </div>
                <h2 id="modal-lead-title">{selectedLead.title}</h2>
              </div>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => setSelectedLead(null)}
                aria-label="Close details"
              >
                <X size={16} />
              </button>
            </div>

            {/* Platform Policy Alert if applicable */}
            {(selectedLead.reply_policy === 'human_only' || selectedLead.platform === 'hackernews') && (
              <div
                className="notice notice-warning"
                style={{ marginTop: 'var(--sp-4)', marginBottom: 'var(--sp-4)' }}
              >
                <ShieldAlert size={18} />
                <div>
                  <strong>Platform Compliance: Manual / Research Only</strong>
                  <span>
                    {selectedLead.platform === 'hackernews'
                      ? 'Hacker News policy forbids generated or AI-assisted comments (March 2026). Use this thread for customer pain research or write an original human comment.'
                      : 'This platform bans automated drafts. Hand-crafted replies only.'}
                  </span>
                </div>
              </div>
            )}

            {/* Thread Health & Opportunity Facts */}
            <div
              style={{
                background: 'var(--surface-subtle)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--r-md)',
                padding: 'var(--sp-4)',
                marginBottom: 'var(--sp-4)',
              }}
            >
              <div
                style={{
                  fontSize: 'var(--fs-xs)',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  color: 'var(--text-subtle)',
                  marginBottom: 'var(--sp-2)',
                }}
              >
                Thread Reply Health & Opportunity
              </div>
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
                  gap: 'var(--sp-2)',
                  fontSize: 'var(--fs-xs)',
                }}
              >
                <div>
                  <span style={{ color: 'var(--text-subtle)' }}>Status: </span>
                  <strong>
                    {selectedLead.thread_health?.commentable === false
                      ? '🔒 Locked/Archived'
                      : '✅ Open for Replies'}
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-subtle)' }}>Discussion: </span>
                  <strong>
                    {selectedLead.thread_health?.num_comments ?? '–'} replies
                  </strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-subtle)' }}>Upvotes: </span>
                  <strong>{selectedLead.thread_health?.score ?? '–'}</strong>
                </div>
                <div>
                  <span style={{ color: 'var(--text-subtle)' }}>Age: </span>
                  <strong>
                    {selectedLead.thread_health?.age_days !== undefined &&
                    selectedLead.thread_health?.age_days !== null
                      ? `${selectedLead.thread_health.age_days} days`
                      : 'Recent'}
                  </strong>
                </div>
              </div>

              {selectedLead.thread_health?.warnings &&
                selectedLead.thread_health.warnings.length > 0 && (
                  <div style={{ marginTop: 'var(--sp-2)', display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                    {selectedLead.thread_health.warnings.map((w, idx) => (
                      <span key={idx} className="badge badge-amber" style={{ fontSize: '11px' }}>
                        <AlertTriangle size={11} style={{ display: 'inline', marginRight: '3px' }} />
                        {w}
                      </span>
                    ))}
                  </div>
                )}
            </div>

            {/* Score Breakdown */}
            <div className="score-breakdown">
              {[
                ['Problem Fit', selectedLead.score_breakdown.problem_fit, 30],
                ['ICP Match', selectedLead.score_breakdown.icp_match, 25],
                ['Buying Intent', selectedLead.score_breakdown.buying_intent, 20],
                ['Pain Urgency', selectedLead.score_breakdown.urgency, 15],
                ['Opportunity', selectedLead.score_breakdown.recency, 10],
              ].map(([label, value, max]) => (
                <div className="score-breakdown-item" key={String(label)}>
                  <span>{label}</span>
                  <strong className="tabular">
                    {value}/{max}
                  </strong>
                </div>
              ))}
              <p>{selectedLead.score_breakdown.explanation}</p>
            </div>

            {selectedLead.platform === 'youtube' && (
              <div className="notice notice-info" style={{ marginBottom: 'var(--sp-4)', fontSize: 'var(--fs-xs)' }}>
                <Video size={16} />
                <div>
                  <strong>YouTube Lead Insight</strong>
                  <span>
                    Replies to YouTube videos and comments are manual by design. Reply Studio prepares value-first advice tailored to the video topic or top comments.
                  </span>
                </div>
              </div>
            )}

            <div className="detail-block">
              <label className="label">Customer Evidence Quote</label>
              <blockquote>&ldquo;{selectedLead.excerpt}&rdquo;</blockquote>
              {selectedLead.evidence && (
                <p style={{ marginTop: 'var(--sp-2)', fontSize: 'var(--fs-xs)', color: 'var(--text-muted)' }}>
                  <strong>Analysis:</strong> {selectedLead.evidence}
                </p>
              )}
            </div>

            <div className="detail-block">
              <label className="label">Product Value & Fit Explanation</label>
              <div className="fit-callout">{selectedLead.product_fit_explanation}</div>
            </div>

            <div className="modal-actions">
              <a
                className="btn btn-secondary"
                href={selectedLead.url}
                target="_blank"
                rel="noreferrer"
              >
                <ExternalLink size={14} />
                <span>Open original discussion</span>
              </a>
              <button
                className="btn btn-primary"
                onClick={() => {
                  const id = selectedLead.id;
                  setSelectedLead(null);
                  onOpenReplyStudio(id);
                }}
              >
                <MessageSquare size={15} />
                <span>
                  {selectedLead.reply_policy === 'human_only' || selectedLead.platform === 'hackernews'
                    ? 'View in Reply Studio'
                    : 'Draft reply in Studio'}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default LeadsView;
