import React, { useState, useEffect, useCallback } from 'react';
import {
  Compass,
  Play,
  RotateCcw,
  HelpCircle,
  XCircle,
  Filter,
  Check,
  ChevronDown,
  ChevronUp,
  Search,
  AlertCircle,
} from 'lucide-react';
import type { BusinessProfile, Campaign, PlatformInfo } from '../types';
import { api } from '../api';

interface DiscoveryViewProps {
  profile: BusinessProfile | null;
  onCampaignFinished: () => void;
  onNavigateToProfile?: () => void;
}

const PLATFORM_LABELS: Record<string, string> = {
  reddit: 'Reddit',
  hackernews: 'Hacker News',
  web: 'Public Web',
  youtube: 'YouTube Discussions',
  quora: 'Quora',
  github: 'GitHub Issues',
  twitter: 'Twitter / X',
};

const STAGE_LABELS: Record<string, string> = {
  switching: 'Switching / Dissatisfaction',
  solution: 'Solution Seeking',
  problem: 'Problem Venting',
  category: 'Category Exploration',
};

function formatDiagnosticKey(key: string): string {
  if (key === 'archived') return 'Archived / locked threads';
  if (key === 'dead_thread') return 'Inactive threads (zero replies)';
  if (key === 'not_discussion') return 'Non-discussion pages (pricing/docs)';
  if (key === 'too_old') return 'Exceeded maximum age cutoff';
  if (key === 'duplicate') return 'Duplicate URLs skipped';
  if (key === 'promotional') return 'Promotional / seller posts';
  if (key === 'crowded') return 'Overcrowded (>80 comments)';
  if (key === 'youtube_comments_disabled') return 'YouTube comments turned off';
  if (key === 'youtube_live_or_upcoming') return 'Live / upcoming YouTube streams skipped';
  if (key === 'youtube_for_kids') return 'Made-for-kids YouTube videos skipped';
  if (key === 'youtube_not_target_language') return 'YouTube videos in other languages skipped';
  if (key.startsWith('youtube_api:')) {
    const sub = key.replace('youtube_api:', '');
    if (sub === 'no_key') return 'YouTube API key unconfigured (using web search fallback)';
    if (sub === 'quota') return 'YouTube daily quota reached';
    if (sub === 'comments_disabled') return 'Comments disabled on YouTube video';
    return `YouTube API (${sub.replaceAll('_', ' ')})`;
  }
  if (key.startsWith('qualifier:')) {
    const sub = key.replace('qualifier:', '');
    if (sub === 'low_score') return 'Below qualification score threshold';
    if (sub === 'spam') return 'Spam or irrelevant patterns';
    if (sub === 'competitor_intel') return 'Classified as competitor intelligence';
    return `Filtered (${sub.replaceAll('_', ' ')})`;
  }
  if (key.startsWith('search_error:')) {
    return `Search query error (${key.replace('search_error:', '')})`;
  }
  if (key === 'reply_draft_failed') return 'Draft generation skipped';
  return key.replaceAll('_', ' ');
}

export const DiscoveryView: React.FC<DiscoveryViewProps> = ({
  profile,
  onCampaignFinished,
  onNavigateToProfile,
}) => {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [campaignName, setCampaignName] = useState(
    profile?.name ? `${profile.name} Discovery Scan` : ''
  );
  const [platformInfo, setPlatformInfo] = useState<PlatformInfo>({
    platforms: ['reddit', 'hackernews', 'web', 'quora', 'github', 'twitter'],
    default: ['reddit', 'hackernews', 'web'],
    weak: ['twitter', 'github'],
  });
  const [selectedPlatforms, setSelectedPlatforms] = useState<string[]>(['reddit', 'hackernews', 'web']);
  const [maxLeads, setMaxLeads] = useState(15);
  const [running, setRunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [activeCampaign, setActiveCampaign] = useState<Campaign | null>(null);
  const [expandedCampaignId, setExpandedCampaignId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'info' | 'error' | 'success'; message: string } | null>(null);

  useEffect(() => {
    if (!campaignName && profile?.name) {
      setCampaignName(`${profile.name} Discovery Scan`);
    }
  }, [profile?.name, campaignName]);

  const loadPlatforms = useCallback(async () => {
    try {
      const info = await api.getPlatforms();
      if (info && info.platforms?.length) {
        setPlatformInfo(info);
        if (info.default?.length) {
          setSelectedPlatforms(info.default);
        }
      }
    } catch {
      // Fallback to defaults
    }
  }, []);

  const loadCampaigns = useCallback(async () => {
    try {
      const list = await api.listCampaigns();
      setCampaigns(list);
      const active = list.find((c) => c.status === 'running');
      if (active) {
        setActiveCampaign(active);
        setRunning(true);
      }
    } catch (e) {
      console.error(e);
    }
  }, []);

  useEffect(() => {
    void loadPlatforms();
    void loadCampaigns();
  }, [loadPlatforms, loadCampaigns]);

  // Poll progress while a campaign is running
  useEffect(() => {
    if (!running || !activeCampaign) return;
    const interval = setInterval(async () => {
      try {
        const updated = await api.getCampaign(activeCampaign.id);
        setActiveCampaign(updated);
        if (updated.status === 'completed' || updated.status === 'failed' || updated.status === 'cancelled') {
          setRunning(false);
          setCancelling(false);
          await loadCampaigns();
          onCampaignFinished();
          if (updated.status === 'completed') {
            setFeedback({
              type: 'success',
              message: `Campaign complete: ${updated.total_qualified} qualified leads discovered across ${updated.total_found} verified discussions.`,
            });
          } else if (updated.status === 'cancelled') {
            setFeedback({
              type: 'info',
              message: 'Campaign execution was stopped by user request.',
            });
          } else {
            setFeedback({
              type: 'error',
              message: updated.current_step || 'Campaign failed. Check server logs for details.',
            });
          }
        }
      } catch {
        setRunning(false);
        setCancelling(false);
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [running, activeCampaign, loadCampaigns, onCampaignFinished]);

  const togglePlatform = (p: string) => {
    if (selectedPlatforms.includes(p)) {
      if (selectedPlatforms.length > 1) {
        setSelectedPlatforms(selectedPlatforms.filter((x) => x !== p));
      }
    } else {
      setSelectedPlatforms([...selectedPlatforms, p]);
    }
  };

  const handleLaunch = async () => {
    if (!profile) {
      setFeedback({
        type: 'error',
        message: 'Please set up your business profile first in the Profile tab.',
      });
      return;
    }
    if (!profile.confirmed) {
      setFeedback({
        type: 'error',
        message: 'Please confirm your Business Profile in the Profile tab before launching autonomous discovery.',
      });
      return;
    }
    setRunning(true);
    setCancelling(false);
    const nameToUse = campaignName.trim() || (profile?.name ? `${profile.name} Discovery Scan` : 'Customer Discovery');
    setFeedback(null);
    try {
      const campId = await api.launchCampaign(nameToUse, selectedPlatforms, maxLeads);
      const camp = await api.getCampaign(campId);
      setActiveCampaign(camp);
      setExpandedCampaignId(campId);
      setFeedback({
        type: 'info',
        message: 'Discovery campaign initiated. Progress updates stream in real-time below.',
      });
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Could not launch campaign.',
      });
      setRunning(false);
    }
  };

  const handleCancelCampaign = async () => {
    if (!activeCampaign) return;
    setCancelling(true);
    try {
      const res = await api.cancelCampaign(activeCampaign.id);
      setFeedback({
        type: 'info',
        message: res.message || 'Cancellation requested. Halting query workers…',
      });
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Could not cancel campaign.',
      });
      setCancelling(false);
    }
  };

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <h1>Discovery Engine</h1>
          <p>
            Scan verified community conversations across Hacker News, Reddit, and public web forums for users actively reporting pain points that match your ICP.
          </p>
        </div>
      </div>

      {feedback && (
        <div
          className={`notice ${
            feedback.type === 'error'
              ? 'notice-error'
              : feedback.type === 'success'
              ? 'notice-success'
              : 'notice-info'
          }`}
          role="status"
        >
          <span>{feedback.message}</span>
          <button className="btn btn-secondary btn-sm" onClick={() => setFeedback(null)}>
            Dismiss
          </button>
        </div>
      )}

      {/* Profile Unconfirmed Warning Banner */}
      {(!profile || !profile.confirmed) && (
        <div className="notice notice-warning" role="alert" style={{ marginBottom: 'var(--sp-6)' }}>
          <AlertCircle size={20} />
          <div>
            <strong>Business profile review required before discovery</strong>
            <span>
              Autonomous query planning requires confirmed ICP parameters, pain vocabulary, and negative guardrails to avoid off-target searches.
            </span>
          </div>
          {onNavigateToProfile && (
            <button className="btn btn-secondary btn-sm" onClick={onNavigateToProfile}>
              Review Profile
            </button>
          )}
        </div>
      )}

      {/* Launch Configuration Panel */}
      <section className="panel" style={{ marginBottom: 'var(--sp-6)' }}>
        <div className="panel-header" style={{ marginBottom: 'var(--sp-5)' }}>
          <div>
            <h2>Configure & Launch Discovery Campaign</h2>
            <p>Select target platforms, search depth, and launch autonomous multi-stage search planning.</p>
          </div>
          <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
            {running && activeCampaign && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleCancelCampaign}
                disabled={cancelling}
                style={{ color: 'var(--danger-text)', borderColor: 'var(--danger-border)' }}
              >
                <XCircle size={15} />
                <span>{cancelling ? 'Stopping Workers…' : 'Cancel Run'}</span>
              </button>
            )}
            <button
              className="btn btn-primary"
              onClick={handleLaunch}
              disabled={running || !profile?.confirmed}
            >
              {running ? <RotateCcw size={16} className="spin" /> : <Play size={16} />}
              <span>{running ? 'Harvesting Discussions…' : 'Launch Customer Discovery'}</span>
            </button>
          </div>
        </div>

        <div className="form-grid-3">
          <div className="form-group">
            <label htmlFor="discovery-campaign-name" className="label">
              Campaign Name
            </label>
            <input
              id="discovery-campaign-name"
              type="text"
              className="input"
              placeholder={profile?.name ? `${profile.name} Discovery Scan` : 'e.g. Q1 Customer Opportunity Hunt'}
              value={campaignName}
              onChange={(e) => setCampaignName(e.target.value)}
              disabled={running}
            />
          </div>

          <div className="form-group">
            <label className="label">
              Discovery Sources ({selectedPlatforms.length} active)
            </label>
            <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
              {platformInfo.platforms.map((p) => {
                const isSelected = selectedPlatforms.includes(p);
                const isWeak = platformInfo.weak?.includes(p);
                const needsKey = platformInfo.needs_key?.includes(p);
                return (
                  <button
                    key={p}
                    type="button"
                    className={`btn btn-sm ${isSelected ? 'btn-primary' : 'btn-secondary'}`}
                    aria-pressed={isSelected}
                    onClick={() => togglePlatform(p)}
                    disabled={running}
                    title={
                      needsKey
                        ? 'Keyed Data API allows comment counts, top comments, & transcripts; web search fallback without key'
                        : isWeak
                        ? 'Secondary platform: lower lead volume or restrictive API rate limits'
                        : undefined
                    }
                  >
                    {isSelected && <Check size={13} />}
                    <span>{PLATFORM_LABELS[p] || p}</span>
                    {needsKey && (
                      <span
                        style={{
                          fontSize: '10px',
                          opacity: 0.9,
                          marginLeft: '4px',
                          fontWeight: 500,
                          padding: '1px 5px',
                          borderRadius: '4px',
                          background: isSelected ? 'rgba(255,255,255,0.25)' : 'var(--warning-bg)',
                          color: isSelected ? 'inherit' : 'var(--warning-text)',
                        }}
                      >
                        API Key
                      </span>
                    )}
                    {isWeak && (
                      <span
                        style={{
                          fontSize: '10px',
                          opacity: 0.85,
                          marginLeft: '2px',
                          fontWeight: 400,
                        }}
                      >
                        (Weak)
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="discovery-max-leads" className="label">
              Max Leads Target
            </label>
            <select
              id="discovery-max-leads"
              className="select"
              value={maxLeads}
              onChange={(e) => setMaxLeads(parseInt(e.target.value, 10))}
              disabled={running}
            >
              <option value="5">Quick Scan (5 Leads)</option>
              <option value="15">Standard Campaign (15 Leads)</option>
              <option value="30">Deep Harvest (30 Leads)</option>
              <option value="50">Comprehensive Search (50 Leads)</option>
              <option value="100">Maximum Harvest (100 Leads)</option>
            </select>
          </div>
        </div>

        {/* Live Progress Bar when active */}
        {activeCampaign && running && (
          <div
            style={{
              marginTop: 'var(--sp-6)',
              padding: 'var(--sp-4)',
              background: 'var(--surface-subtle)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--r-md)',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 'var(--fs-sm)',
                fontWeight: 600,
                marginBottom: 'var(--sp-2)',
              }}
            >
              <span style={{ color: 'var(--primary)' }}>{activeCampaign.current_step}</span>
              <span className="tabular">{activeCampaign.progress_percentage}%</span>
            </div>
            <div className="coverage-bar" style={{ height: '8px' }}>
              <span
                style={{
                  width: `${activeCampaign.progress_percentage}%`,
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
            <div
              style={{
                display: 'flex',
                gap: 'var(--sp-4)',
                marginTop: 'var(--sp-3)',
                fontSize: 'var(--fs-xs)',
                color: 'var(--text-muted)',
                flexWrap: 'wrap',
              }}
            >
              <span>Discovered: <strong className="tabular">{activeCampaign.total_found}</strong> conversations</span>
              <span>Qualified: <strong className="tabular">{activeCampaign.total_qualified}</strong> leads</span>
              <span>High Potential: <strong className="tabular">{activeCampaign.high_potential_count}</strong></span>
              {cancelling && (
                <span style={{ color: 'var(--danger)', fontWeight: 600 }}>
                  Halting background search workers…
                </span>
              )}
            </div>

            {/* Quality Filtering Diagnostics */}
            {activeCampaign.diagnostics && Object.keys(activeCampaign.diagnostics).length > 0 && (
              <div
                style={{
                  marginTop: 'var(--sp-3)',
                  paddingTop: 'var(--sp-3)',
                  borderTop: '1px solid var(--border)',
                }}
              >
                <div
                  style={{
                    fontSize: 'var(--fs-xs)',
                    fontWeight: 600,
                    color: 'var(--text-subtle)',
                    marginBottom: 'var(--sp-2)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 'var(--sp-1)',
                  }}
                >
                  <Filter size={13} />
                  <span>Quality Diagnostics (Filtered Out):</span>
                </div>
                <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                  {Object.entries(activeCampaign.diagnostics).map(([key, count]) => (
                    <span
                      key={key}
                      className="badge badge-low"
                      style={{ fontSize: 'var(--fs-2xs)' }}
                    >
                      {formatDiagnosticKey(key)}: <strong className="tabular">{count}</strong>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Discovery Strategy Explainer */}
      <section
        className="card"
        style={{
          padding: 'var(--sp-5)',
          background: 'var(--surface-subtle)',
          marginBottom: 'var(--sp-6)',
        }}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--sp-2)',
            fontWeight: 700,
            fontSize: 'var(--fs-base)',
            color: 'var(--text-main)',
            marginBottom: 'var(--sp-3)',
          }}
        >
          <HelpCircle size={16} /> Autonomous Query Generation & Thread Checks
        </div>
        <div className="form-grid-3">
          <div>
            <strong style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-main)' }}>Multi-Stage Query Planning</strong>
            <p style={{ marginTop: '4px', fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', lineHeight: '1.45' }}>
              Formulates distinct queries across 4 buyer funnel stages: Problem Venting, Solution Seeking, Switching / Dissatisfaction, and Category Exploration.
            </p>
          </div>
          <div>
            <strong style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-main)' }}>Thread Opportunity Checks</strong>
            <p style={{ marginTop: '4px', fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', lineHeight: '1.45' }}>
              Verifies post age, reply counts, lock/archive status, and overcrowding (&gt;80 comments) to ensure high visibility for every interaction.
            </p>
          </div>
          <div>
            <strong style={{ fontSize: 'var(--fs-sm)', color: 'var(--text-main)' }}>Transparent Quality Filtering</strong>
            <p style={{ marginTop: '4px', fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', lineHeight: '1.45' }}>
              Screens out self-promotional listicles, pricing pages, and low-relevance threads, surfacing diagnostic metrics on every run.
            </p>
          </div>
        </div>
      </section>

      {/* Campaign History & Query Inspection */}
      <section className="panel lead-table-panel">
        <div className="table-header">
          <div>
            <h2>Campaign History</h2>
            <span>Past discovery jobs, qualification yields, and generated queries</span>
          </div>
        </div>

        {campaigns.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Compass size={20} />
            </div>
            <strong>No campaigns run yet</strong>
            <span>Configure target sources above and launch your first autonomous customer discovery run.</span>
          </div>
        ) : (
          <div className="priority-list">
            {campaigns.map((c) => {
              const isExpanded = expandedCampaignId === c.id;
              return (
                <div
                  key={c.id}
                  style={{
                    padding: 'var(--sp-4) var(--sp-5)',
                    borderBottom: '1px solid var(--border)',
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      gap: 'var(--sp-4)',
                      flexWrap: 'wrap',
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 'var(--fs-base)', color: 'var(--text-main)' }}>
                        {c.name}
                      </div>
                      <div
                        style={{
                          fontSize: 'var(--fs-xs)',
                          color: 'var(--text-subtle)',
                          display: 'flex',
                          gap: 'var(--sp-3)',
                          marginTop: '2px',
                          flexWrap: 'wrap',
                        }}
                      >
                        <span>
                          Sources: {c.selected_platforms.map((p) => PLATFORM_LABELS[p] || p).join(', ')}
                        </span>
                        <span>• Queries Planned: {c.queries?.length || 0}</span>
                        {c.current_step && <span>• {c.current_step}</span>}
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-4)' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, color: 'var(--text-main)' }}>
                          <span className="tabular">{c.total_qualified}</span> Leads Qualified
                        </div>
                        <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--success)' }}>
                          <span className="tabular">{c.high_potential_count}</span> High Potential
                        </div>
                      </div>
                      <span
                        className={`badge ${
                          c.status === 'completed'
                            ? 'badge-high'
                            : c.status === 'running'
                            ? 'badge-medium'
                            : c.status === 'cancelled'
                            ? 'badge-amber'
                            : 'badge-low'
                        }`}
                      >
                        {c.status === 'cancelled' ? 'Cancelled' : c.status}
                      </span>

                      {c.queries && c.queries.length > 0 && (
                        <button
                          type="button"
                          className="icon-btn"
                          onClick={() => setExpandedCampaignId(isExpanded ? null : c.id)}
                          aria-label={isExpanded ? 'Collapse queries' : 'Expand queries'}
                          title="Inspect planned queries"
                        >
                          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Quality Diagnostics chips */}
                  {c.diagnostics && Object.keys(c.diagnostics).length > 0 && (
                    <div
                      style={{
                        marginTop: 'var(--sp-2)',
                        display: 'flex',
                        gap: 'var(--sp-2)',
                        flexWrap: 'wrap',
                      }}
                    >
                      {Object.entries(c.diagnostics).map(([key, count]) => (
                        <span
                          key={key}
                          style={{
                            fontSize: '11px',
                            color: 'var(--text-subtle)',
                            background: 'var(--surface-subtle)',
                            padding: '2px 6px',
                            borderRadius: 'var(--r-xs)',
                            border: '1px solid var(--border)',
                          }}
                        >
                          {formatDiagnosticKey(key)}: <strong className="tabular">{count}</strong>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Expandable Planned Queries */}
                  {isExpanded && c.queries && c.queries.length > 0 && (
                    <div
                      style={{
                        marginTop: 'var(--sp-3)',
                        padding: 'var(--sp-3)',
                        background: 'var(--surface-subtle)',
                        borderRadius: 'var(--r-md)',
                        border: '1px solid var(--border)',
                      }}
                    >
                      <div
                        style={{
                          fontSize: 'var(--fs-xs)',
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                          color: 'var(--text-subtle)',
                          marginBottom: 'var(--sp-2)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '6px',
                        }}
                      >
                        <Search size={12} />
                        <span>Planned Queries ({c.queries.length})</span>
                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-2)' }}>
                        {c.queries.map((q, qIdx) => (
                          <div
                            key={q.id || qIdx}
                            style={{
                              padding: 'var(--sp-2) var(--sp-3)',
                              background: 'var(--surface)',
                              border: '1px solid var(--border)',
                              borderRadius: 'var(--r-sm)',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              gap: 'var(--sp-3)',
                              fontSize: 'var(--fs-xs)',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', flex: 1, minWidth: 0 }}>
                              <span className="badge badge-low">{PLATFORM_LABELS[q.platform] || q.platform}</span>
                              {q.stage && (
                                <span className="badge badge-medium" style={{ fontSize: '10px' }}>
                                  {STAGE_LABELS[q.stage] || q.stage}
                                </span>
                              )}
                              <span style={{ fontWeight: 600, color: 'var(--text-main)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                &ldquo;{q.query}&rdquo;
                              </span>
                            </div>
                            {q.target_community && (
                              <span style={{ color: 'var(--text-subtle)', fontSize: 'var(--fs-2xs)', flexShrink: 0 }}>
                                {q.target_community}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};

export default DiscoveryView;
