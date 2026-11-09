import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Users,
  Play,
  Square,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  FileText,
  Brain,
  Sparkles,
  ExternalLink,
  ThumbsUp,
  ThumbsDown,
  Trash2,
  Plus,
  ShieldCheck,
  ArrowRight,
  LoaderCircle,
  Check,
  X,
  MessageSquare,
  Search,
  Database,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  Send,
} from 'lucide-react';
import type {
  DirectiveDetail,
  DirectiveSummary,
  TeamReport,
  TeamRoster,
  MemoryItem,
  BusinessProfile,
  CEOIntakeState,
} from '../types';
import { api } from '../api';

interface TeamViewProps {
  profile: BusinessProfile | null;
  onNavigateToLeads: () => void;
  onNavigateToReplyStudio: (leadId?: string) => void;
  onNavigateToProfile: () => void;
}

const roleIcons: Record<string, string> = {
  analyst: '🏢',
  scout: '🔍',
  qualifier: '🎯',
  writer: '✍️',
  editor: '📝',
  strategist: '📊',
  researcher: '🔬',
  follow_up: '🔄',
  inspector: '🛡️',
  owner: '👑',
};

const intentLabels: Record<string, string> = {
  find_customers: 'Find Customers',
  draft_replies: 'Draft Replies',
  review_drafts: 'Review Drafts',
  weekly_review: 'Weekly Review',
  setup_voice: 'Voice Setup',
  market_research: 'Market Research',
  follow_up: 'Follow Up',
  custom: 'Custom Directive',
};

export const TeamView: React.FC<TeamViewProps> = ({
  profile,
  onNavigateToLeads,
  onNavigateToReplyStudio,
  onNavigateToProfile,
}) => {
  const [directives, setDirectives] = useState<DirectiveSummary[]>([]);
  const [selectedDirectiveId, setSelectedDirectiveId] = useState<string | null>(null);
  const [directiveDetail, setDirectiveDetail] = useState<DirectiveDetail | null>(null);
  const [modelConfigured, setModelConfigured] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [promptMessage, setPromptMessage] = useState<string>('');
  const [notice, setNotice] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  // Checkpoint modal / resolution state
  const [checkpointFeedback, setCheckpointFeedback] = useState<Record<string, string>>({});
  const [resolvingTaskId, setResolvingTaskId] = useState<string | null>(null);

  // Report modal
  const [report, setReport] = useState<TeamReport | null>(null);
  const [reportLoading, setReportLoading] = useState<boolean>(false);
  const [showReportModal, setShowReportModal] = useState<boolean>(false);

  // Roster & Memory state
  const [showRosterModal, setShowRosterModal] = useState<boolean>(false);
  const [roster, setRoster] = useState<TeamRoster | null>(null);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [newMemoryText, setNewMemoryText] = useState<string>('');

  // CEO Intake state
  const [intakeState, setIntakeState] = useState<CEOIntakeState | null>(null);
  const [intakeInput, setIntakeInput] = useState<string>('');
  const [intakeSubmitting, setIntakeSubmitting] = useState<boolean>(false);
  const [showIntakeSection, setShowIntakeSection] = useState<boolean>(true);
  const [showFactsSummary, setShowFactsSummary] = useState<boolean>(false);

  const pollTimerRef = useRef<number | null>(null);
  const intakePollRef = useRef<number | null>(null);

  const starterPrompts = [
    {
      title: 'Find Customers',
      prompt: profile?.url
        ? `Find customers for ${profile.url}`
        : 'Find customers for our product and qualify active discussions',
    },
    {
      title: 'Review Competitors',
      prompt: 'Research competitors and alternative products in our market space',
    },
    {
      title: 'Draft Replies',
      prompt: 'Draft high-converting replies for qualified leads in the queue',
    },
    {
      title: 'Weekly Review',
      prompt: 'Review weekly discovery performance, account safety, and high-impact discussions',
    },
  ];

  const fetchDirectives = useCallback(async (selectFirst = false) => {
    try {
      const data = await api.team.listDirectives();
      setDirectives(data.directives || []);
      setModelConfigured(data.model_configured);
      if (selectFirst && data.directives && data.directives.length > 0 && !selectedDirectiveId) {
        setSelectedDirectiveId(data.directives[0].directive_id);
      }
    } catch (err) {
      console.error('Failed to fetch directives:', err);
    }
  }, [selectedDirectiveId]);

  const fetchDirectiveDetail = useCallback(async (id: string) => {
    try {
      const detail = await api.team.getDirective(id);
      setDirectiveDetail(detail);
    } catch (err) {
      console.error('Failed to fetch directive detail:', err);
    }
  }, []);

  const fetchRosterAndMemory = useCallback(async () => {
    try {
      const [rosterData, memoryData] = await Promise.all([
        api.team.getRoster(),
        api.team.getMemory(),
      ]);
      setRoster(rosterData);
      setMemories(memoryData || []);
    } catch (err) {
      console.error('Failed to load roster or memories:', err);
    }
  }, []);

  const fetchIntake = useCallback(async () => {
    try {
      const data = await api.team.getIntake();
      setIntakeState(data);
    } catch (err) {
      console.error('Failed to fetch intake state:', err);
    }
  }, []);

  // Initial load
  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([
        fetchDirectives(true),
        fetchRosterAndMemory(),
        fetchIntake(),
      ]);
      setLoading(false);
    };
    void init();
  }, [fetchDirectives, fetchRosterAndMemory, fetchIntake]);

  // Polling for live intake background search jobs
  useEffect(() => {
    const isSearching = intakeState?.jobs?.some((j) => j.status === 'running');
    if (isSearching) {
      intakePollRef.current = window.setInterval(() => {
        void fetchIntake();
      }, 3500);
    }
    return () => {
      if (intakePollRef.current) {
        clearInterval(intakePollRef.current);
      }
    };
  }, [intakeState?.jobs, fetchIntake]);

  // Load detail when selectedDirectiveId changes
  useEffect(() => {
    if (selectedDirectiveId) {
      void fetchDirectiveDetail(selectedDirectiveId);
    } else {
      setDirectiveDetail(null);
    }
  }, [selectedDirectiveId, fetchDirectiveDetail]);

  // Polling for active directives
  useEffect(() => {
    if (!selectedDirectiveId) return;

    const shouldPoll =
      directiveDetail?.status === 'running' ||
      directiveDetail?.status === 'open' ||
      directiveDetail?.tasks.some((t) => t.status === 'running' || t.status === 'pending');

    if (shouldPoll) {
      pollTimerRef.current = window.setInterval(() => {
        void fetchDirectiveDetail(selectedDirectiveId);
        void fetchDirectives(false);
      }, 3000);
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
      }
    };
  }, [selectedDirectiveId, directiveDetail?.status, directiveDetail?.tasks, fetchDirectiveDetail, fetchDirectives]);

  const handleAskCeo = async (e?: React.FormEvent, overridePrompt?: string) => {
    if (e) e.preventDefault();
    const query = (overridePrompt || promptMessage).trim();
    if (!query) return;

    setActionLoading(true);
    setNotice(null);
    try {
      const res = await api.team.ask(query);
      setPromptMessage('');
      setNotice({
        type: 'success',
        text: `CEO planned directive: ${res.intent}. Work is underway!`,
      });
      await fetchDirectives();
      setSelectedDirectiveId(res.directive_id);
      await fetchDirectiveDetail(res.directive_id);
    } catch (err) {
      setNotice({
        type: 'error',
        text: err instanceof Error ? err.message : 'Could not submit directive to CEO.',
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleRunDirective = async (id: string) => {
    setActionLoading(true);
    try {
      await api.team.runDirective(id);
      setNotice({ type: 'success', text: 'Directive execution resumed.' });
      await fetchDirectiveDetail(id);
      await fetchDirectives();
    } catch (err) {
      setNotice({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to run directive.',
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelDirective = async (id: string) => {
    if (!confirm('Are you sure you want to stop this directive? Active tasks will be skipped.')) return;
    setActionLoading(true);
    try {
      await api.team.cancelDirective(id, 'Owner requested stop');
      setNotice({ type: 'info', text: 'Directive cancelled.' });
      await fetchDirectiveDetail(id);
      await fetchDirectives();
    } catch (err) {
      setNotice({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to cancel directive.',
      });
    } finally {
      setActionLoading(false);
    }
  };

  const handleResolveCheckpoint = async (taskId: string, decision: 'approve' | 'reject') => {
    const message = (checkpointFeedback[taskId] || (decision === 'approve' ? 'Approved by owner' : 'Rejected by owner')).trim();
    setResolvingTaskId(taskId);
    try {
      await api.team.resolveCheckpoint(taskId, decision, message);
      setNotice({
        type: 'success',
        text: `Checkpoint ${decision === 'approve' ? 'approved' : 'rejected'}. Team resuming.`,
      });
      if (selectedDirectiveId) {
        await fetchDirectiveDetail(selectedDirectiveId);
        await fetchDirectives();
      }
    } catch (err) {
      setNotice({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to resolve checkpoint.',
      });
    } finally {
      setResolvingTaskId(null);
    }
  };

  const handleOpenReport = async (id: string) => {
    setReportLoading(true);
    setShowReportModal(true);
    try {
      const rep = await api.team.getReport(id);
      setReport(rep);
    } catch (err) {
      setNotice({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to fetch verified report.',
      });
      setShowReportModal(false);
    } finally {
      setReportLoading(false);
    }
  };

  const handleAddMemory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newMemoryText.trim() || newMemoryText.length < 8) {
      setNotice({ type: 'error', text: 'Standing preference must be at least 8 characters.' });
      return;
    }
    try {
      await api.team.addMemory(newMemoryText.trim());
      setNewMemoryText('');
      await fetchRosterAndMemory();
      setNotice({ type: 'success', text: 'Company preference saved for all specialists.' });
    } catch (err) {
      setNotice({ type: 'error', text: err instanceof Error ? err.message : 'Could not add preference.' });
    }
  };

  const handleDeleteMemory = async (id: number) => {
    try {
      await api.team.deleteMemory(id);
      await fetchRosterAndMemory();
      setNotice({ type: 'info', text: 'Preference deleted.' });
    } catch (err) {
      setNotice({ type: 'error', text: err instanceof Error ? err.message : 'Could not delete preference.' });
    }
  };

  const handleSubmitIntake = async (key: string, isSkip: boolean = false) => {
    if (!isSkip && !intakeInput.trim()) return;
    setIntakeSubmitting(true);
    try {
      const answers = isSkip ? undefined : { [key]: intakeInput.trim() };
      const skip = isSkip ? [key] : undefined;
      const res = await api.team.submitIntake(answers, skip);
      setIntakeState(res);
      setIntakeInput('');
      setNotice({
        type: 'success',
        text: isSkip
          ? 'Question skipped.'
          : 'Answer saved! CEO and live harvester updated.',
      });
      if (res.directive_id) {
        await fetchDirectives();
        setSelectedDirectiveId(res.directive_id);
      }
    } catch (err) {
      setNotice({
        type: 'error',
        text: err instanceof Error ? err.message : 'Failed to submit intake answer.',
      });
    } finally {
      setIntakeSubmitting(false);
    }
  };

  const handleResetIntake = async () => {
    if (!confirm('Restart the CEO interview? This clears answered facts so you can profile a new product.')) return;
    setIntakeSubmitting(true);
    try {
      const res = await api.team.resetIntake();
      setIntakeState(res);
      setIntakeInput('');
      setNotice({ type: 'info', text: 'Intake interview has been reset.' });
    } catch (err) {
      setNotice({
        type: 'error',
        text: err instanceof Error ? err.message : 'Could not reset intake.',
      });
    } finally {
      setIntakeSubmitting(false);
    }
  };

  const handleLaunchIntakeDirective = async () => {
    if (!intakeState?.suggested_request) return;
    await handleAskCeo(undefined, intakeState.suggested_request);
  };

  const getStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'running':
        return 'badge-primary';
      case 'completed':
      case 'done':
        return 'badge-success';
      case 'waiting_owner':
      case 'needs_owner':
        return 'badge-warning';
      case 'escalated':
      case 'needs_ceo':
      case 'failed':
        return 'badge-danger';
      case 'cancelled':
      case 'skipped':
        return 'badge-muted';
      default:
        return 'badge-secondary';
    }
  };

  const getTrustBadgeClass = (trust: string) => {
    switch (trust) {
      case 'high':
        return 'trust-high';
      case 'medium':
        return 'trust-medium';
      case 'low':
        return 'trust-low';
      default:
        return 'trust-none';
    }
  };

  const pendingCheckpoints = directiveDetail?.tasks.filter(
    (t) => t.kind === 'checkpoint' && t.status === 'needs_owner'
  ) || [];

  return (
    <div className="page-shell team-page">
      {/* Page Header */}
      <section className="page-heading team-heading">
        <div>
          <div className="title-row">
            <h1>CEO & Autonomous Squad</h1>
            <span className={`status-pill ${modelConfigured ? 'status-pill-green' : 'status-pill-amber'}`}>
              {modelConfigured ? 'Autonomous Server Mode' : 'Host Assistant Mode'}
            </span>
          </div>
          <p>
            Instruct your CEO to orchestrate specialists across research, qualification, drafting, and post inspection. Every output is strictly verified before reporting.
          </p>
        </div>
        <div className="heading-actions">
          <button
            className="btn btn-secondary"
            onClick={() => {
              void fetchRosterAndMemory();
              setShowRosterModal(true);
            }}
          >
            <Users size={15} />
            <span>Squad Roster & Memory ({memories.length})</span>
          </button>
        </div>
      </section>

      {/* Notice Banner */}
      {notice && (
        <aside className={`notice notice-${notice.type}`}>
          {notice.type === 'error' ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}
          <span>{notice.text}</span>
          <button className="toast-dismiss" onClick={() => setNotice(null)}>
            <X size={14} />
          </button>
        </aside>
      )}

      {/* CEO Interactive Intake & Real-time Harvester */}
      <section className="ceo-intake-section">
        <div
          className="intake-header-bar"
          onClick={() => setShowIntakeSection(!showIntakeSection)}
        >
          <div className="intake-header-left">
            <span className="intake-avatar">🎙️</span>
            <div className="intake-header-text">
              <h3>
                <span>CEO Intake Interview & Live Harvester</span>
                {intakeState?.jobs && intakeState.jobs.some((j) => j.status === 'running') && (
                  <span className="job-status-pill job-status-running">
                    <span className="pulse-dot" />
                    Searching Live Sources
                  </span>
                )}
              </h3>
              <p>
                Direct dialogue with your CEO to establish product value and ICP. Searches launch in the background as soon as product and users are identified.
              </p>
            </div>
          </div>
          <div className="intake-header-right">
            {(intakeState?.prefetched_threads ?? 0) > 0 && (
              <span
                className="intake-prefetched-pill"
                title="Harvested early in background and waiting for Scout to claim"
              >
                <Database size={13} />
                <span>{intakeState?.prefetched_threads} Threads Prefetched</span>
              </span>
            )}
            <button className="btn-icon" aria-label="Toggle Intake">
              {showIntakeSection ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          </div>
        </div>

        {showIntakeSection && (
          <div className="intake-body">
            {intakeState?.ask_next && intakeState.ask_next.length > 0 ? (
              <div className="intake-question-card">
                <div className="intake-question-header">
                  <div>
                    <span className="intake-question-tag">
                      {intakeState.missing_required.some((m) => m.key === intakeState.ask_next[0].key)
                        ? 'Required for Search'
                        : 'Optimization Question'}
                    </span>
                    <h4 className="intake-question-prompt">
                      {intakeState.ask_next[0].question}
                    </h4>
                    <p className="intake-question-why">
                      <strong>Why CEO asks:</strong> {intakeState.ask_next[0].why}
                    </p>
                  </div>
                </div>

                <div className="intake-input-box">
                  <textarea
                    className="intake-textarea"
                    placeholder="Enter your answer in your own words (e.g. pain points, where they talk, competitors, site, voice habits)..."
                    value={intakeInput}
                    onChange={(e) => setIntakeInput(e.target.value)}
                    disabled={intakeSubmitting}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                        void handleSubmitIntake(intakeState.ask_next[0].key, false);
                      }
                    }}
                  />
                  <div className="intake-actions-row">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleSubmitIntake(intakeState.ask_next[0].key, true)}
                      disabled={intakeSubmitting}
                      title="Skip this question for now"
                    >
                      Skip Question
                    </button>
                    <button
                      type="button"
                      className="btn btn-primary btn-sm"
                      onClick={() => handleSubmitIntake(intakeState.ask_next[0].key, false)}
                      disabled={intakeSubmitting || !intakeInput.trim()}
                    >
                      {intakeSubmitting ? (
                        <LoaderCircle size={14} className="spin" />
                      ) : (
                        <Send size={14} />
                      )}
                      <span>Submit Answer (Ctrl+Enter)</span>
                    </button>
                  </div>
                </div>
              </div>
            ) : intakeState?.suggested_request ? (
              <div className="intake-completed-card">
                <div className="title-row">
                  <CheckCircle2 size={18} className="text-success" />
                  <strong>Intake Interview Complete & Ready for Pipeline</strong>
                </div>
                <p style={{ margin: 0, fontSize: '13px' }}>
                  The CEO has gathered the essential context and preliminary searches have primed the discovery queue.
                </p>
                <div className="intake-brief-box">
                  {intakeState.suggested_request}
                </div>
                <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={handleResetIntake}
                    disabled={actionLoading}
                  >
                    <RotateCcw size={13} />
                    <span>Reset & Start Over</span>
                  </button>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={handleLaunchIntakeDirective}
                    disabled={actionLoading}
                  >
                    <Sparkles size={13} />
                    <span>Launch Autonomous Directive with this Brief</span>
                  </button>
                </div>
              </div>
            ) : null}

            {/* Live Search Background Jobs */}
            {intakeState?.jobs && intakeState.jobs.length > 0 && (
              <div className="intake-jobs-section">
                <h4>
                  <Search size={14} />
                  <span>Live Harvester Status</span>
                </h4>
                <div className="intake-jobs-grid">
                  {intakeState.jobs.map((job) => (
                    <div key={job.id} className="intake-job-card">
                      <div className="job-top-row">
                        <span className="job-platform-name">
                          {job.platform === 'youtube'
                            ? 'YouTube (Transcripts & Comments)'
                            : job.platform === 'hackernews'
                            ? 'Hacker News'
                            : job.platform}
                        </span>
                        <span className={`job-status-pill job-status-${job.status}`}>
                          {job.status === 'running' && <span className="pulse-dot" />}
                          {job.status === 'done' && <Check size={11} />}
                          {job.status === 'failed' && <AlertTriangle size={11} />}
                          {job.status}
                        </span>
                      </div>
                      <div className="job-metrics-row">
                        <span><strong>{job.queries ?? 0}</strong> queries</span>
                        <span><strong>{job.threads ?? 0}</strong> threads found</span>
                      </div>
                      {job.communities && job.communities.length > 0 && (
                        <div className="job-communities-text">
                          Top: {job.communities.map((c) => `${c.name} (${c.threads})`).join(', ')}
                        </div>
                      )}
                      {job.summary && (
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                          {job.summary}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Collapsible Facts Summary */}
            {intakeState?.collected && Object.keys(intakeState.collected).length > 0 && (
              <div className="intake-facts-summary">
                <div
                  style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                  onClick={() => setShowFactsSummary(!showFactsSummary)}
                >
                  <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-muted)' }}>
                    Known Company Facts ({Object.keys(intakeState.collected).length})
                  </span>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <button
                      type="button"
                      className="btn-link-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        void handleResetIntake();
                      }}
                      style={{ fontSize: '11px', color: 'var(--danger)' }}
                    >
                      Clear / Reset
                    </button>
                    {showFactsSummary ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                  </div>
                </div>
                {showFactsSummary && (
                  <div className="facts-chips-list">
                    {Object.entries(intakeState.collected).map(([k, v]) => (
                      <div key={k} className="fact-chip" title={v}>
                        <strong>{k}:</strong> {v.length > 40 ? `${v.slice(0, 40)}…` : v}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </section>

      {/* CEO Prompt Box */}
      <section className="ceo-command-section">
        <form onSubmit={handleAskCeo} className="ceo-prompt-form">
          <div className="ceo-input-wrapper">
            <span className="ceo-avatar">👑</span>
            <input
              type="text"
              className="ceo-input"
              placeholder="Tell the CEO what to do (e.g. 'Find customers for https://myapp.com', 'Review competitor complaints')..."
              value={promptMessage}
              onChange={(e) => setPromptMessage(e.target.value)}
              disabled={actionLoading}
            />
            <button
              type="submit"
              className="btn btn-primary ceo-submit-btn"
              disabled={actionLoading || !promptMessage.trim()}
            >
              {actionLoading ? <LoaderCircle size={15} className="spin" /> : <Sparkles size={15} />}
              <span>Ask CEO</span>
            </button>
          </div>
        </form>

        <div className="starter-prompts-bar">
          <span className="starter-prompts-label">Quick playbooks:</span>
          {starterPrompts.map((p, idx) => (
            <button
              key={idx}
              className="starter-chip"
              onClick={() => handleAskCeo(undefined, p.prompt)}
              disabled={actionLoading}
            >
              {p.title}
            </button>
          ))}
        </div>
      </section>

      {/* Main Grid: Directives List & Active Mission Control */}
      <div className="team-layout-grid">
        {/* Left Column: Directives History */}
        <aside className="directives-sidebar">
          <div className="directives-sidebar-header">
            <h3>Directives History</h3>
            <button
              className="btn-icon"
              onClick={() => fetchDirectives()}
              title="Refresh directives"
            >
              <RefreshCw size={14} />
            </button>
          </div>

          {loading ? (
            <div className="loading-state-sm">
              <LoaderCircle size={18} className="spin" />
              <span>Loading missions…</span>
            </div>
          ) : directives.length === 0 ? (
            <div className="empty-box">
              <p>No directives yet.</p>
              <span>Ask the CEO above to launch your first mission.</span>
            </div>
          ) : (
            <div className="directives-list">
              {directives.map((dir) => {
                const isSelected = dir.directive_id === selectedDirectiveId;
                return (
                  <button
                    key={dir.directive_id}
                    className={`directive-nav-item ${isSelected ? 'active' : ''}`}
                    onClick={() => setSelectedDirectiveId(dir.directive_id)}
                  >
                    <div className="directive-item-top">
                      <span className="directive-intent">
                        {intentLabels[dir.intent] || dir.intent}
                      </span>
                      <span className={`badge ${getStatusBadgeClass(dir.status)}`}>
                        {dir.status}
                      </span>
                    </div>
                    <div className="directive-request-preview" title={dir.request}>
                      {dir.request}
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        {/* Right Column: Mission Pipeline / DAG Visualizer */}
        <main className="directive-detail-pane">
          {!directiveDetail ? (
            <div className="empty-state-card">
              <Brain size={40} className="text-muted" />
              <h3>Select or launch a directive</h3>
              <p>
                Choose an existing mission from the list or send an instruction to your CEO to start autonomous customer discovery.
              </p>
            </div>
          ) : (
            <div className="directive-mission-card">
              {/* Directive Header */}
              <div className="mission-header">
                <div>
                  <div className="mission-badges">
                    <span className="badge badge-secondary">
                      {intentLabels[directiveDetail.intent] || directiveDetail.intent}
                    </span>
                    <span className={`badge ${getStatusBadgeClass(directiveDetail.status)}`}>
                      {directiveDetail.status.toUpperCase()}
                    </span>
                    <span className="mission-id">#{directiveDetail.directive_id}</span>
                  </div>
                  <h2 className="mission-title">{directiveDetail.request}</h2>
                </div>

                <div className="mission-actions">
                  {directiveDetail.status === 'running' ||
                  directiveDetail.status === 'open' ||
                  directiveDetail.status === 'waiting_owner' ? (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => handleCancelDirective(directiveDetail.directive_id)}
                      disabled={actionLoading}
                    >
                      <Square size={13} />
                      <span>Stop Mission</span>
                    </button>
                  ) : null}

                  {directiveDetail.status === 'open' ||
                  directiveDetail.status === 'waiting_owner' ? (
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => handleRunDirective(directiveDetail.directive_id)}
                      disabled={actionLoading}
                    >
                      <Play size={13} />
                      <span>Run Next Task</span>
                    </button>
                  ) : null}

                  <button
                    className="btn btn-primary btn-sm"
                    onClick={() => handleOpenReport(directiveDetail.directive_id)}
                  >
                    <FileText size={13} />
                    <span>View Verified Report</span>
                  </button>
                </div>
              </div>

              {/* Progress Bar */}
              <div className="progress-section">
                <div className="progress-label-row">
                  <span>
                    Task Pipeline Progress: {directiveDetail.progress.done} / {directiveDetail.progress.total}
                  </span>
                  <span>{directiveDetail.next}</span>
                </div>
                <div className="progress-bar-bg">
                  <div
                    className="progress-bar-fill"
                    style={{
                      width: `${
                        directiveDetail.progress.total > 0
                          ? (directiveDetail.progress.done / directiveDetail.progress.total) * 100
                          : 0
                      }%`,
                    }}
                  />
                </div>
              </div>

              {/* Pending Checkpoints Banner (Human in the loop) */}
              {pendingCheckpoints.length > 0 && (
                <div className="checkpoint-alert-box" role="alert">
                  <div className="checkpoint-alert-header">
                    <AlertTriangle size={18} className="text-warning" />
                    <strong>Owner Approval Required to Proceed</strong>
                  </div>

                  {pendingCheckpoints.map((cp) => (
                    <div key={cp.task_id} className="checkpoint-card">
                      <div className="checkpoint-title">
                        {cp.title}
                        {cp.checkpoint === 'confirm_profile' && (
                          <button
                            className="btn-link-sm"
                            onClick={onNavigateToProfile}
                            style={{ marginLeft: '10px' }}
                          >
                            Inspect Profile in Tab →
                          </button>
                        )}
                      </div>
                      <p className="checkpoint-instruction">
                        {cp.instruction || 'Please review the generated output and confirm to continue the pipeline.'}
                      </p>

                      <div className="checkpoint-action-row">
                        <input
                          type="text"
                          className="checkpoint-feedback-input"
                          placeholder="Optional feedback or adjustment instructions for the specialist..."
                          value={checkpointFeedback[cp.task_id] || ''}
                          onChange={(e) =>
                            setCheckpointFeedback((prev) => ({
                              ...prev,
                              [cp.task_id]: e.target.value,
                            }))
                          }
                          disabled={resolvingTaskId === cp.task_id}
                        />

                        <div className="checkpoint-buttons">
                          <button
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleResolveCheckpoint(cp.task_id, 'reject')}
                            disabled={resolvingTaskId === cp.task_id}
                          >
                            <ThumbsDown size={13} />
                            <span>Request Changes</span>
                          </button>
                          <button
                            className="btn btn-primary btn-sm"
                            onClick={() => handleResolveCheckpoint(cp.task_id, 'approve')}
                            disabled={resolvingTaskId === cp.task_id}
                          >
                            {resolvingTaskId === cp.task_id ? (
                              <LoaderCircle size={13} className="spin" />
                            ) : (
                              <ThumbsUp size={13} />
                            )}
                            <span>Approve & Continue</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Task Pipeline (DAG Cards) */}
              <div className="pipeline-container">
                <h3 className="section-title">Specialist Workflow Pipeline</h3>
                <div className="task-flow-list">
                  {directiveDetail.tasks.map((task, idx) => {
                    const isRunning = task.status === 'running';
                    const isDone = task.status === 'done';
                    const isNeedsOwner = task.status === 'needs_owner';
                    const isEscalated = task.status === 'escalated';
                    const isSkipped = task.status === 'skipped';

                    return (
                      <div
                        key={task.task_id}
                        className={`task-node-card ${
                          isRunning
                            ? 'task-node-running'
                            : isDone
                            ? 'task-node-done'
                            : isNeedsOwner
                            ? 'task-node-owner'
                            : isEscalated
                            ? 'task-node-escalated'
                            : isSkipped
                            ? 'task-node-skipped'
                            : ''
                        }`}
                      >
                        <div className="task-node-left">
                          <div className="task-step-number">{idx + 1}</div>
                          <div className="task-role-icon">
                            {roleIcons[task.role] || '🤖'}
                          </div>
                          <div className="task-info">
                            <div className="task-title-line">
                              <span className="task-role-name">
                                {task.role.toUpperCase()}
                              </span>
                              <strong className="task-title">{task.title}</strong>
                            </div>
                            {task.instruction && (
                              <p className="task-instruction-text">{task.instruction}</p>
                            )}
                            {task.issues && task.issues.length > 0 && (
                              <div className="task-issue-tag">
                                <AlertTriangle size={12} />
                                <span>{task.issues[task.issues.length - 1]}</span>
                              </div>
                            )}
                          </div>
                        </div>

                        <div className="task-node-right">
                          {task.attempts > 1 && (
                            <span className="task-attempt-badge">
                              Attempt {task.attempts}/3
                            </span>
                          )}
                          <span className={`badge ${getStatusBadgeClass(task.status)}`}>
                            {isRunning && <LoaderCircle size={12} className="spin" />}
                            {isDone && <Check size={12} />}
                            {task.status}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Notes & Audit Log */}
              {directiveDetail.events && directiveDetail.events.length > 0 && (
                <div className="audit-events-section">
                  <h4 className="events-title">Execution Audit Trail</h4>
                  <div className="events-list">
                    {directiveDetail.events.slice(-6).map((ev, i) => (
                      <div key={i} className="event-row">
                        <span className="event-time">
                          {new Date(ev.at * 1000).toLocaleTimeString()}
                        </span>
                        <span className="event-kind">{ev.kind}</span>
                        <span className="event-note">{ev.note}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </main>
      </div>

      {/* Verified Report Modal */}
      {showReportModal && (
        <div className="modal-backdrop" onClick={() => setShowReportModal(false)}>
          <div className="modal-dialog report-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="report-header-title">
                <ShieldCheck size={20} className="text-success" />
                <h2>Verified Intelligence Report</h2>
                {report && (
                  <span className={`trust-badge ${getTrustBadgeClass(report.trust)}`}>
                    Trust: {report.trust.toUpperCase()}
                  </span>
                )}
              </div>
              <button
                className="modal-close-btn"
                onClick={() => setShowReportModal(false)}
              >
                <X size={18} />
              </button>
            </div>

            <div className="modal-body report-modal-body">
              {reportLoading ? (
                <div className="loading-state">
                  <LoaderCircle size={24} className="spin" />
                  <span>Loading verified audit trail and lead cards…</span>
                </div>
              ) : !report ? (
                <div className="empty-box">No report available.</div>
              ) : (
                <div className="report-content">
                  {/* Headline */}
                  <div className="report-headline-card">
                    <h3>{report.headline}</h3>
                    <p>{report.summary}</p>
                  </div>

                  {/* Quality Metrics */}
                  <div className="quality-grid">
                    <div className="quality-card">
                      <span className="quality-num">{report.stats.leads}</span>
                      <span className="quality-label">Leads Discovered</span>
                    </div>
                    <div className="quality-card">
                      <span className="quality-num">{report.ledger.evidence_items}</span>
                      <span className="quality-label">Evidence Items In Ledger</span>
                    </div>
                    <div className="quality-card">
                      <span className="quality-num">{report.quality.revision_rounds}</span>
                      <span className="quality-label">Editor Revisions</span>
                    </div>
                    <div className="quality-card">
                      <span className="quality-num">{report.quality.tool_calls}</span>
                      <span className="quality-label">Tool Calls Verified</span>
                    </div>
                  </div>

                  {/* Lead Cards */}
                  {report.lead_cards && report.lead_cards.length > 0 && (
                    <div className="report-lead-cards-section">
                      <h4>Discovered Leads with Verbatim Evidence</h4>
                      <div className="report-lead-list">
                        {report.lead_cards.map((c) => (
                          <div key={c.lead_id} className="lead-report-item">
                            <div className="lead-item-header">
                              <div>
                                <span className="platform-tag">{c.platform}</span>
                                <strong className="lead-title">{c.title}</strong>
                              </div>
                              <div className="lead-score-pill">Score: {c.score}</div>
                            </div>

                            <blockquote className="lead-evidence-quote">
                              "{c.evidence_quote}"
                              {c.quote_verified && (
                                <span className="quote-verified-badge" title="Word-for-word quote verified in fetched page">
                                  <Check size={11} /> Verified Quote
                                </span>
                              )}
                            </blockquote>

                            {c.reply && (
                              <div className="draft-preview-box">
                                <div className="draft-preview-header">
                                  <span>Draft Reply ({c.reply.status})</span>
                                  {c.reply.gate && (
                                    <span
                                      className={`gate-badge ${
                                        c.reply.gate.ready ? 'gate-ready' : 'gate-waiting'
                                      }`}
                                    >
                                      Pre-Post Gate: {c.reply.gate.code} ({c.reply.gate.message})
                                    </span>
                                  )}
                                </div>
                                <p className="draft-text">
                                  {c.reply.value_first || c.reply.product_aware || 'Draft pending generation'}
                                </p>
                              </div>
                            )}

                            <div className="lead-item-actions">
                              <a
                                href={c.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="btn btn-secondary btn-xs"
                              >
                                <ExternalLink size={12} />
                                <span>Open Thread</span>
                              </a>
                              <button
                                className="btn btn-primary btn-xs"
                                onClick={() => {
                                  setShowReportModal(false);
                                  onNavigateToReplyStudio(c.lead_id);
                                }}
                              >
                                <MessageSquare size={12} />
                                <span>Open in Reply Studio</span>
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Automated 27 Posting Gates Inspection Results */}
                  {report.inspection && report.inspection.length > 0 && (
                    <div className="report-inspection-section">
                      <div className="inspection-section-header">
                        <ShieldCheck size={18} className="text-primary" />
                        <div>
                          <h4>Automated Safety & Pre-Post Inspection Gates</h4>
                          <p className="inspection-subtitle">
                            Every generated draft is inspected against 27 posting gates (thread reply limit of 2-3, 60m min thread gap, 7-day community cool-off, platform caps, disclosure phrasing, and safety bounds).
                          </p>
                        </div>
                      </div>

                      <div className="inspection-table-wrapper">
                        <table className="inspection-table">
                          <thead>
                            <tr>
                              <th>Thread / Target</th>
                              <th>Gate Status</th>
                              <th>Gate Code</th>
                              <th>Audit Finding</th>
                              <th>Attention Flags</th>
                              <th>Action</th>
                            </tr>
                          </thead>
                          <tbody>
                            {report.inspection.map((row, idx) => (
                              <tr
                                key={row.reply_id || idx}
                                className={`inspection-row ${
                                  row.ready ? 'row-ready' : row.waits ? 'row-wait' : 'row-blocked'
                                }`}
                              >
                                <td className="inspection-title-cell">
                                  <strong>{row.title || `Reply #${(row.reply_id || '').slice(-6)}`}</strong>
                                </td>
                                <td>
                                  <span
                                    className={`status-pill ${
                                      row.ready
                                        ? 'status-pill-green'
                                        : row.waits
                                        ? 'status-pill-amber'
                                        : 'status-pill-rose'
                                    }`}
                                  >
                                    {row.ready ? 'Ready to Post' : row.waits ? 'Wait Gap Required' : 'Inspection Blocked'}
                                  </span>
                                </td>
                                <td>
                                  <code className="gate-code-badge">{row.code}</code>
                                </td>
                                <td>
                                  <div className="gate-detail-cell">
                                    <span className="gate-msg">{row.message}</span>
                                    {row.editor_verdict && (
                                      <span className="gate-verdict">Editor: {row.editor_verdict}</span>
                                    )}
                                  </div>
                                </td>
                                <td>
                                  {row.attention && row.attention.length > 0 ? (
                                    <div className="attention-tags">
                                      {row.attention.map((att, aIdx) => (
                                        <span key={aIdx} className="attention-tag">
                                          {att}
                                        </span>
                                      ))}
                                    </div>
                                  ) : (
                                    <span className="text-muted" style={{ fontSize: '11px' }}>None (clean)</span>
                                  )}
                                </td>
                                <td>
                                  <button
                                    className="btn btn-secondary btn-xs"
                                    onClick={() => {
                                      setShowReportModal(false);
                                      onNavigateToReplyStudio(row.reply_id);
                                    }}
                                  >
                                    <MessageSquare size={12} />
                                    <span>Review</span>
                                  </button>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* What Was Tried if Empty */}
                  {report.what_was_tried && report.what_was_tried.length > 0 && (
                    <div className="report-tried-box">
                      <h4>What Was Executed During Search</h4>
                      <ul>
                        {report.what_was_tried.map((line, idx) => (
                          <li key={idx}>{line}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Owner Next Actions */}
                  {report.owner_actions && report.owner_actions.length > 0 && (
                    <div className="report-actions-box">
                      <h4>Recommended Next Actions</h4>
                      <ul className="action-checklist">
                        {report.owner_actions.map((act, i) => (
                          <li key={i}>
                            <ArrowRight size={14} className="text-primary" />
                            <span>{act}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                className="btn btn-secondary"
                onClick={() => setShowReportModal(false)}
              >
                Close Report
              </button>
              <button
                className="btn btn-primary"
                onClick={() => {
                  setShowReportModal(false);
                  onNavigateToLeads();
                }}
              >
                <span>View All Leads in Inbox</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Roster & Memory Modal */}
      {showRosterModal && (
        <div className="modal-backdrop" onClick={() => setShowRosterModal(false)}>
          <div className="modal-dialog roster-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-row">
                <Users size={18} />
                <h2>Company Squad Roster & Standing Memory</h2>
              </div>
              <button className="modal-close-btn" onClick={() => setShowRosterModal(false)}>
                <X size={18} />
              </button>
            </div>

            <div className="modal-body roster-modal-body">
              {/* Roster Specialists */}
              <section className="roster-section">
                <h3>Specialist Team Members</h3>
                <div className="roster-grid">
                  {roster?.roles.map((r) => (
                    <div key={r.name} className="specialist-card">
                      <div className="specialist-header">
                        <span className="specialist-icon">{roleIcons[r.name] || '🤖'}</span>
                        <div>
                          <strong>{r.title}</strong>
                          <span className="specialist-name">@{r.name}</span>
                        </div>
                        <span className="badge badge-secondary">{r.tier}</span>
                      </div>
                      <div className="specialist-tools">
                        <strong>Allowed Tools:</strong>
                        <div className="tool-chips">
                          {r.tools.slice(0, 4).map((t) => (
                            <span key={t} className="tool-chip">
                              {t}
                            </span>
                          ))}
                          {r.tools.length > 4 && (
                            <span className="tool-chip-more">+{r.tools.length - 4} more</span>
                          )}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </section>

              {/* Company Memory Section */}
              <section className="memory-section">
                <div className="memory-header-row">
                  <div>
                    <h3>Standing Company Memory</h3>
                    <p>
                      Rules and preferences recorded here are automatically provided in every specialist's work order.
                    </p>
                  </div>
                </div>

                <form onSubmit={handleAddMemory} className="add-memory-form">
                  <input
                    type="text"
                    className="form-input"
                    placeholder="Add standing preference (e.g. 'Never mention competitor prices directly', 'Always prioritize indie founders')..."
                    value={newMemoryText}
                    onChange={(e) => setNewMemoryText(e.target.value)}
                  />
                  <button type="submit" className="btn btn-primary btn-sm">
                    <Plus size={14} />
                    <span>Add Preference</span>
                  </button>
                </form>

                <div className="memory-list">
                  {memories.length === 0 ? (
                    <p className="text-muted" style={{ fontSize: '13px' }}>
                      No standing company preferences stored yet.
                    </p>
                  ) : (
                    memories.map((m) => (
                      <div key={m.id} className="memory-item">
                        <div className="memory-item-content">
                          <span className="memory-category-tag">{m.category}</span>
                          <span className="memory-text">{m.text}</span>
                        </div>
                        <button
                          className="btn-icon text-danger"
                          onClick={() => handleDeleteMemory(m.id)}
                          title="Delete preference"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    ))
                  )}
                </div>
              </section>
            </div>

            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowRosterModal(false)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
