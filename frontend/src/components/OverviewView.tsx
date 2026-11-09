import React from 'react';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Compass,
  ExternalLink,
  MessageSquare,
  ShieldCheck,
  Target,
  Sparkles,
  Users,
} from 'lucide-react';
import type { BusinessProfile, LeadQualification } from '../types';

interface OverviewViewProps {
  profile: BusinessProfile | null;
  leads: LeadQualification[];
  leadCounts: Record<string, number>;
  onNavigate: (tab: string, leadId?: string) => void;
  onLaunchCampaign: () => void;
}

const classificationLabel = (value: string) =>
  value.replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

export const OverviewView: React.FC<OverviewViewProps> = ({
  profile,
  leads,
  leadCounts,
  onNavigate,
  onLaunchCampaign,
}) => {
  const priorityLeads = leads
    .filter((lead) => lead.classification === 'high_potential' || lead.score >= 75)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5);

  const sourceCount = new Set(leads.map((lead) => lead.platform)).size;
  const qualified = (leadCounts.high_potential || 0) + (leadCounts.relevant || 0);
  const needsReview = leads.filter((lead) => lead.score >= 50 && lead.purchase_intent !== 'None').length;

  return (
    <div className="page-shell overview-page">
      <section className="page-heading overview-heading">
        <div>
          <h1>Turn public customer pain into conversations</h1>
          <p>
            AgentReach finds problem-aware discussions, surfaces clear evidence, and helps you craft high-converting replies safely.
          </p>
        </div>
        <div className="heading-actions">
          <button className="btn btn-secondary" onClick={() => onNavigate('leads')}>
            <span>Review queue</span>
            <ArrowRight size={15} />
          </button>
          <button
            className="btn btn-primary"
            onClick={onLaunchCampaign}
            disabled={!profile?.confirmed}
            title={!profile?.confirmed ? 'Confirm business profile before launching discovery' : undefined}
          >
            <Compass size={15} />
            <span>Launch discovery</span>
          </button>
        </div>
      </section>

      {!profile ? (
        <section className="notice notice-warning" role="status">
          <AlertCircle size={20} />
          <div>
            <strong>Set up your business profile first</strong>
            <span>AgentReach needs a confirmed product profile to match ICP and score buying signals.</span>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => onNavigate('profile')}>
            Create profile
          </button>
        </section>
      ) : !profile.confirmed ? (
        <section className="notice notice-info" role="status">
          <Target size={20} />
          <div>
            <strong>{profile.name || 'Business profile'} is ready for review</strong>
            <span>Review and confirm the extracted ICP facts before running autonomous discovery.</span>
          </div>
          <button className="btn btn-secondary btn-sm" onClick={() => onNavigate('profile')}>
            Review profile
          </button>
        </section>
      ) : null}

      <section className="overview-team-card">
        <div className="overview-team-left">
          <div className="overview-team-icon">
            <Users size={20} />
          </div>
          <div className="overview-team-text">
            <h3>Autonomous CEO & Specialist Squad</h3>
            <p>
              Instruct your squad to find leads, verify evidence quotes, and draft safety-inspected replies autonomously.
            </p>
          </div>
        </div>
        <button className="btn btn-primary btn-sm" onClick={() => onNavigate('team')}>
          <Sparkles size={14} />
          <span>Launch with CEO</span>
        </button>
      </section>

      <section className="metric-grid" aria-label="Discovery summary">
        <article className="metric-card metric-card-primary">
          <div className="metric-label">Discovered Conversations</div>
          <div className="metric-value">{leadCounts.total || 0}</div>
          <div className="metric-meta">
            <span className="status-dot status-dot-blue" />
            <span>{sourceCount || 0} sources in queue</span>
          </div>
        </article>

        <article className="metric-card">
          <div className="metric-label">Qualified Leads</div>
          <div className="metric-value">{qualified}</div>
          <div className="metric-meta">
            <span className="status-dot status-dot-green" />
            <span>Score 50+ with intent signals</span>
          </div>
        </article>

        <article className="metric-card">
          <div className="metric-label">High-Potential Signals</div>
          <div className="metric-value">{leadCounts.high_potential || 0}</div>
          <div className="metric-meta">
            <span className="status-dot status-dot-amber" />
            <span>Urgent buying intent</span>
          </div>
        </article>

        <article className="metric-card">
          <div className="metric-label">Awaiting Human Review</div>
          <div className="metric-value">{needsReview}</div>
          <div className="metric-meta">
            <ShieldCheck size={14} />
            <span>Protected draft queue</span>
          </div>
        </article>
      </section>

      <section className="overview-grid">
        <article className="panel priority-panel">
          <div className="panel-header">
            <div>
              <h2>Priority Conversations</h2>
              <p>Top discussions scored on problem fit, urgency, and purchase intent.</p>
            </div>
          </div>

          {priorityLeads.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <Compass size={22} />
              </div>
              <strong>No priority conversations yet</strong>
              <span>Confirm your business profile and launch discovery to populate your opportunities.</span>
              <button
                className="btn btn-primary btn-sm"
                onClick={onLaunchCampaign}
                disabled={!profile?.confirmed}
              >
                Launch first campaign
              </button>
            </div>
          ) : (
            <div className="priority-list">
              {priorityLeads.map((lead) => (
                <div className="priority-row" key={lead.id}>
                  <div className="score-ring" aria-label={`Score ${lead.score} out of 100`}>
                    <strong>{lead.score}</strong>
                    <span>/100</span>
                  </div>

                  <div className="priority-copy">
                    <div className="priority-meta" style={{ flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
                      <span className="badge badge-high">{classificationLabel(lead.classification)}</span>
                      <span>{lead.platform} · {lead.community}</span>
                      {lead.judged_by === 'llm' && (
                        <span className="badge badge-low" style={{ fontSize: '10px' }}>
                          AI Judged
                        </span>
                      )}
                      {lead.thread_health?.commentable === false && (
                        <span className="badge badge-danger" style={{ fontSize: '10px' }}>
                          Locked
                        </span>
                      )}
                    </div>
                    <h3>{lead.title}</h3>
                    <p>{lead.customer_problem}</p>
                    <div className="evidence-line">&ldquo;{lead.excerpt}&rdquo;</div>
                  </div>

                  <div className="priority-actions">
                    <span
                      className={`intent-pill ${lead.urgency === 'High' ? 'intent-pill-urgent' : ''}`}
                    >
                      {lead.purchase_intent} intent
                    </span>
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => onNavigate('reply_studio', lead.id)}
                    >
                      <MessageSquare size={13} />
                      <span>Draft reply</span>
                    </button>
                    <a
                      className="icon-btn"
                      href={lead.url}
                      target="_blank"
                      rel="noreferrer"
                      aria-label={`Open external discussion: ${lead.title}`}
                    >
                      <ExternalLink size={14} />
                    </a>
                  </div>
                </div>
              ))}
            </div>
          )}
        </article>

        <aside className="panel control-panel">
          <h2>Safe by Default</h2>
          <p style={{ marginTop: '6px', color: 'var(--text-muted)', fontSize: 'var(--fs-xs)', lineHeight: '1.5' }}>
            AgentReach separates research, drafting, human approval, and publishing to ensure automated spam never occurs.
          </p>

          <div className="status-stack">
            <div className="status-row">
              <span className="status-icon status-icon-green">
                <CheckCircle2 size={16} />
              </span>
              <div>
                <strong>Evidence-Backed Scoring</strong>
                <span>Each score includes transparent ICP match breakdowns and original quotes.</span>
              </div>
            </div>

            <div className="status-row">
              <span className="status-icon status-icon-blue">
                <MessageSquare size={16} />
              </span>
              <div>
                <strong>Helpful, Disclosed Drafts</strong>
                <span>Value-first and product-aware variants are fully editable before posting.</span>
              </div>
            </div>

            <div className="status-row">
              <span className="status-icon status-icon-amber">
                <ShieldCheck size={16} />
              </span>
              <div>
                <strong>Human In The Loop</strong>
                <span>Replies remain in draft state until you manually review and confirm them.</span>
              </div>
            </div>
          </div>
        </aside>
      </section>

      <section className="panel coverage-panel">
        <div className="panel-header" style={{ marginBottom: 'var(--sp-2)' }}>
          <div>
            <h2>Platform Coverage Breakdown</h2>
            <p>Distribution of qualified discussions across indexed communities.</p>
          </div>
        </div>

        <div className="coverage-grid">
          {[
            { id: 'reddit', label: 'Reddit' },
            { id: 'hackernews', label: 'Hacker News' },
            { id: 'web', label: 'Public Web' },
            { id: 'quora', label: 'Quora' },
            { id: 'github', label: 'GitHub' },
            { id: 'twitter', label: 'Twitter / X' },
          ].map((item) => {
            const count = leads.filter((lead) => lead.platform === item.id).length;
            const pct = leads.length > 0 ? (count / leads.length) * 100 : 0;
            return (
              <div className="coverage-item" key={item.id}>
                <span className="coverage-name">{item.label}</span>
                <strong>{count}</strong>
                <span className="coverage-bar">
                  <span style={{ width: `${Math.min(100, count ? Math.max(8, pct) : 0)}%` }} />
                </span>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
};

export default OverviewView;
