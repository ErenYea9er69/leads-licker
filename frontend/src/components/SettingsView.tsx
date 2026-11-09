import React, { useState, useEffect, useCallback } from 'react';
import {
  Save,
  Download,
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  ShieldCheck,
  Database,
  Users,
  Link2,
  Trash2,
  Plus,
  Volume2,
  Globe,
  RefreshCw,
  Check,
  X,
  Info,
  Copy,
  Terminal,
} from 'lucide-react';
import type {
  PostingSettings,
  LLMSettings,
  MCPSettings,
  LinkedAccountDetail,
  ConnectionsGuide,
} from '../types';
import { api } from '../api';

export const SettingsView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<
    'accounts' | 'connections' | 'safety' | 'ai_storage' | 'mcp_ai' | 'export'
  >('accounts');
  const [copiedSnippet, setCopiedSnippet] = useState<string | null>(null);

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSnippet(id);
    setTimeout(() => setCopiedSnippet(null), 2500);
  };

  // Settings State
  const [postingSettings, setPostingSettings] = useState<PostingSettings>({
    mode: 'manual',
    daily_limit: 5,
    min_interval_seconds: 600,
    interval_jitter: 0.3,
    max_mention_ratio: 0.1,
    require_account_health: true,
    require_rules_ack: true,
    max_replies_per_thread: 2,
    min_thread_gap_minutes: 60,
    product_community_gap_days: 7,
    allowed_communities: [],
    emergency_stop: false,
    reddit_client_id: '',
    reddit_client_secret: '',
    reddit_username: '',
    reddit_password: '',
    github_token: '',
    has_reddit_password: false,
    has_reddit_client_secret: false,
    has_github_token: false,
  });

  const [llmSettings, setLlmSettings] = useState<LLMSettings>({
    provider: 'gemini',
    model: 'gemini-2.5-flash',
    api_key: '',
    has_api_key: false,
    configured: false,
  });

  const [mcpSettings, setMcpSettings] = useState<MCPSettings>({
    discovery_mode: 'host_driven',
    default_output_format: 'both',
    default_min_score: 70,
    default_export_path: './discovery_exports',
    emergency_stop: false,
    auto_launch_dashboard: false,
  });

  const [dbSyncMode, setDbSyncMode] = useState<'DEFAULT' | 'NORMAL' | 'EXTRA' | 'OFF'>('NORMAL');
  const [auditorProvider, setAuditorProvider] = useState<string>('');
  const [auditorModel, setAuditorModel] = useState<string>('');

  // Linked Accounts State
  const [accounts, setAccounts] = useState<LinkedAccountDetail[]>([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);
  const [newAccountPlatform, setNewAccountPlatform] = useState('reddit');
  const [newAccountHandle, setNewAccountHandle] = useState('');
  const [newAccountAlias, setNewAccountAlias] = useState('');
  const [newAccountFocus, setNewAccountFocus] = useState('');
  const [newAccountMode, setNewAccountMode] = useState<'manual' | 'api'>('manual');
  const [showAddAccount, setShowAddAccount] = useState(false);

  // Per-account voice editing
  const [editingVoiceAccount, setEditingVoiceAccount] = useState<string | null>(null);
  const [voiceSampleText, setVoiceSampleText] = useState('');

  // Connections Guide State
  const [connectionsGuide, setConnectionsGuide] = useState<ConnectionsGuide | null>(null);
  const [loadingConnections, setLoadingConnections] = useState(false);

  // Status & Feedback
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const loadSettings = useCallback(async () => {
    try {
      const data = await api.getSettings();
      if (data.posting_settings) {
        setPostingSettings((prev) => ({
          ...prev,
          ...data.posting_settings,
          max_replies_per_thread: data.posting_settings.max_replies_per_thread ?? 2,
          min_thread_gap_minutes: data.posting_settings.min_thread_gap_minutes ?? 60,
          product_community_gap_days: data.posting_settings.product_community_gap_days ?? 7,
          interval_jitter: data.posting_settings.interval_jitter ?? 0.3,
          max_mention_ratio: data.posting_settings.max_mention_ratio ?? 0.1,
          require_account_health: data.posting_settings.require_account_health ?? true,
          require_rules_ack: data.posting_settings.require_rules_ack ?? true,
          reddit_password: '',
          reddit_client_secret: '',
          github_token: '',
        }));
      }
      if (data.llm_settings) {
        setLlmSettings((prev) => ({
          ...prev,
          ...data.llm_settings,
          api_key: '',
        }));
      }
      if (data.mcp_settings) {
        setMcpSettings(data.mcp_settings);
      }
    } catch (e) {
      setErrorMessage(e instanceof Error ? e.message : 'Could not load current settings.');
    }
  }, []);

  const loadAccounts = useCallback(async () => {
    setLoadingAccounts(true);
    try {
      const list = await api.getAccounts();
      setAccounts(list);
    } catch (e) {
      // quiet fallback
    } finally {
      setLoadingAccounts(false);
    }
  }, []);

  const loadConnections = useCallback(async () => {
    setLoadingConnections(true);
    try {
      const guide = await api.getConnections();
      setConnectionsGuide(guide);
    } catch (e) {
      // quiet fallback
    } finally {
      setLoadingConnections(false);
    }
  }, []);

  useEffect(() => {
    void loadSettings();
    void loadAccounts();
    void loadConnections();
  }, [loadSettings, loadAccounts, loadConnections]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setErrorMessage(null);
    try {
      const postPayload: Partial<PostingSettings> = { ...postingSettings };
      if (!postPayload.reddit_password) delete postPayload.reddit_password;
      if (!postPayload.reddit_client_secret) delete postPayload.reddit_client_secret;
      if (!postPayload.github_token) delete postPayload.github_token;

      const llmPayload: Partial<LLMSettings> = {
        provider: llmSettings.provider,
        model: llmSettings.model,
      };
      if (llmSettings.api_key && llmSettings.api_key.trim()) {
        llmPayload.api_key = llmSettings.api_key.trim();
      }

      await api.updateSettings({
        posting_settings: postPayload,
        llm_settings: llmPayload,
        mcp_settings: mcpSettings,
      });

      setSavedMessage('Platform settings saved successfully. Changes applied to active engine.');
      await loadSettings();
      setTimeout(() => setSavedMessage(null), 3500);
    } catch (err: any) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleLinkAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAccountHandle.trim()) return;
    setSaving(true);
    setErrorMessage(null);
    try {
      const focusList = newAccountFocus
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean);
      await api.linkAccount({
        platform: newAccountPlatform,
        handle: newAccountHandle.trim(),
        alias: newAccountAlias.trim() || undefined,
        focus: focusList.length > 0 ? focusList : undefined,
        mode: newAccountMode,
      });
      setSavedMessage(`Account @${newAccountHandle.trim()} linked successfully on ${newAccountPlatform}!`);
      setNewAccountHandle('');
      setNewAccountAlias('');
      setNewAccountFocus('');
      setShowAddAccount(false);
      await loadAccounts();
      await loadConnections();
      setTimeout(() => setSavedMessage(null), 3500);
    } catch (err: any) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to link account.');
    } finally {
      setSaving(false);
    }
  };

  const handleUnlinkAccount = async (platform: string, handle: string) => {
    if (!window.confirm(`Unlink @${handle} on ${platform}?`)) return;
    try {
      await api.unlinkAccount(platform, handle);
      setSavedMessage(`Unlinked @${handle}.`);
      await loadAccounts();
      await loadConnections();
      setTimeout(() => setSavedMessage(null), 3000);
    } catch (err: any) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to unlink account.');
    }
  };

  const handleSaveVoice = async (platform: string, handle: string) => {
    if (!voiceSampleText.trim()) return;
    try {
      const samples = voiceSampleText
        .split('\n---\n')
        .map((s) => s.trim())
        .filter(Boolean);
      await api.setAccountVoice(platform, handle, samples.length > 0 ? samples : [voiceSampleText.trim()]);
      setSavedMessage(`Voice samples updated for @${handle}!`);
      setEditingVoiceAccount(null);
      setVoiceSampleText('');
      await loadAccounts();
      setTimeout(() => setSavedMessage(null), 3000);
    } catch (err: any) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to update voice samples.');
    }
  };

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <h1>Settings & Safety Controls</h1>
          <p>
            Manage multi-account personas, verify platform connections, enforce thread safety rules, and configure AI providers.
          </p>
        </div>
      </div>

      {savedMessage && (
        <div className="notice notice-success" role="status">
          <CheckCircle2 size={16} />
          <span>{savedMessage}</span>
        </div>
      )}
      {errorMessage && (
        <div className="notice notice-error" role="alert">
          <AlertTriangle size={16} />
          <span>{errorMessage}</span>
          <button className="btn btn-secondary btn-sm" onClick={() => setErrorMessage(null)}>
            Dismiss
          </button>
        </div>
      )}

      {/* Settings Navigation Tabs */}
      <div className="version-toggle-bar" style={{ marginBottom: 'var(--sp-5)' }}>
        <button
          type="button"
          className={`version-tab ${activeTab === 'accounts' ? 'active' : ''}`}
          onClick={() => setActiveTab('accounts')}
        >
          <Users size={14} style={{ display: 'inline', marginRight: '6px' }} />
          Accounts & Voices ({accounts.length})
        </button>
        <button
          type="button"
          className={`version-tab ${activeTab === 'connections' ? 'active' : ''}`}
          onClick={() => setActiveTab('connections')}
        >
          <Globe size={14} style={{ display: 'inline', marginRight: '6px' }} />
          Sources & Connections Guide
        </button>
        <button
          type="button"
          className={`version-tab ${activeTab === 'safety' ? 'active' : ''}`}
          onClick={() => setActiveTab('safety')}
        >
          <ShieldCheck size={14} style={{ display: 'inline', marginRight: '6px' }} />
          Thread Rules & Safety
        </button>
        <button
          type="button"
          className={`version-tab ${activeTab === 'ai_storage' ? 'active' : ''}`}
          onClick={() => setActiveTab('ai_storage')}
        >
          <Cpu size={14} style={{ display: 'inline', marginRight: '6px' }} />
          AI & Storage Config
        </button>
        <button
          type="button"
          className={`version-tab ${activeTab === 'mcp_ai' ? 'active' : ''}`}
          onClick={() => setActiveTab('mcp_ai')}
        >
          <Terminal size={14} style={{ display: 'inline', marginRight: '6px' }} />
          AI Clients & MCP Integration
        </button>
        <button
          type="button"
          className={`version-tab ${activeTab === 'export' ? 'active' : ''}`}
          onClick={() => setActiveTab('export')}
        >
          <Download size={14} style={{ display: 'inline', marginRight: '6px' }} />
          Data Export
        </button>
      </div>

      {/* ── TAB 1: ACCOUNTS & VOICES ── */}
      {activeTab === 'accounts' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-6)' }}>
          <section className="panel">
            <div className="panel-header" style={{ flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
              <div>
                <h2>Linked Accounts & Multi-Persona Manager</h2>
                <p>
                  Link your authentic accounts across Reddit, GitHub, YouTube, X, and web forums. The engine tracks age, karma, and health to enforce pitch levels and safely rotate accounts per community.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={() => setShowAddAccount(!showAddAccount)}
              >
                {showAddAccount ? <X size={14} /> : <Plus size={14} />}
                <span>{showAddAccount ? 'Close Form' : 'Link New Account'}</span>
              </button>
            </div>

            {/* Link Account Form */}
            {showAddAccount && (
              <form onSubmit={handleLinkAccount} className="card" style={{ padding: 'var(--sp-5)', marginBottom: 'var(--sp-5)', background: 'var(--surface-subtle)' }}>
                <h3 style={{ fontSize: 'var(--fs-base)', fontWeight: 700, marginBottom: 'var(--sp-3)' }}>Link a Platform Account</h3>
                <div className="form-grid-3" style={{ marginBottom: 'var(--sp-3)' }}>
                  <div className="form-group">
                    <label className="label">Platform</label>
                    <select
                      className="select"
                      value={newAccountPlatform}
                      onChange={(e) => setNewAccountPlatform(e.target.value)}
                    >
                      <option value="reddit">Reddit</option>
                      <option value="github">GitHub</option>
                      <option value="youtube">YouTube</option>
                      <option value="twitter">X (Twitter)</option>
                      <option value="hackernews">Hacker News</option>
                      <option value="quora">Quora</option>
                      <option value="web">Web Forum</option>
                    </select>
                  </div>

                  <div className="form-group">
                    <label className="label">Account Handle / Username</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. founder_john or @channel"
                      value={newAccountHandle}
                      onChange={(e) => setNewAccountHandle(e.target.value)}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="label">Variable Alias (Optional)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. alt1, personal (used in env vars)"
                      value={newAccountAlias}
                      onChange={(e) => setNewAccountAlias(e.target.value)}
                    />
                  </div>
                </div>

                <div className="form-grid-2" style={{ marginBottom: 'var(--sp-4)' }}>
                  <div className="form-group">
                    <label className="label">Focus Communities (Optional comma-separated)</label>
                    <input
                      type="text"
                      className="input"
                      placeholder="e.g. r/startups, r/SaaS, r/freelance"
                      value={newAccountFocus}
                      onChange={(e) => setNewAccountFocus(e.target.value)}
                    />
                    <span className="helper-text">Account is preferred when replying in these communities.</span>
                  </div>

                  <div className="form-group">
                    <label className="label">Posting Mode</label>
                    <select
                      className="select"
                      value={newAccountMode}
                      onChange={(e) => setNewAccountMode(e.target.value as any)}
                    >
                      <option value="manual">Manual Copy & Confirm (Safe)</option>
                      <option value="api">API Automation (Requires env credentials)</option>
                    </select>
                  </div>
                </div>

                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--sp-2)' }}>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowAddAccount(false)}>
                    Cancel
                  </button>
                  <button type="submit" className="btn btn-primary btn-sm" disabled={saving}>
                    <Link2 size={14} />
                    <span>Confirm & Link Account</span>
                  </button>
                </div>
              </form>
            )}

            {/* Accounts List */}
            {loadingAccounts ? (
              <div style={{ padding: 'var(--sp-8)', textAlign: 'center', color: 'var(--text-muted)' }}>
                Loading linked accounts…
              </div>
            ) : accounts.length === 0 ? (
              <div className="empty-state card" style={{ padding: 'var(--sp-8)' }}>
                <Users size={28} style={{ color: 'var(--text-muted)', marginBottom: 'var(--sp-2)' }} />
                <strong>No accounts linked yet</strong>
                <span>
                  Link at least one account so AgentReach can assess health, calculate karma safety limits, and draft personalized voice responses.
                </span>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() => setShowAddAccount(true)}
                  style={{ marginTop: 'var(--sp-3)' }}
                >
                  <Plus size={14} />
                  <span>Link Your First Account</span>
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
                {accounts.map((acc) => {
                  const healthStageLabels: Record<number, string> = {
                    0: 'Stage 0: Build (Max Pitch: Level 0)',
                    1: 'Stage 1: Trusted (Max Pitch: Level 1)',
                    2: 'Stage 2: Established (Max Pitch: Level 2)',
                    3: 'Stage 3: Veteran (Max Pitch: Level 3)',
                  };

                  const isEditingVoice = editingVoiceAccount === `${acc.platform}:${acc.handle}`;

                  return (
                    <div key={`${acc.platform}:${acc.handle}`} className="card" style={{ padding: 'var(--sp-5)' }}>
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                          marginBottom: 'var(--sp-3)',
                          flexWrap: 'wrap',
                          gap: 'var(--sp-2)',
                        }}
                      >
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', flexWrap: 'wrap' }}>
                            <span className="badge badge-primary">{acc.platform}</span>
                            <strong style={{ fontSize: 'var(--fs-base)', color: 'var(--text-main)' }}>
                              @{acc.handle}
                            </strong>
                            {acc.alias && (
                              <span className="badge badge-low" title="Alias used in env variable names">
                                Alias: {acc.alias}
                              </span>
                            )}
                            <span className={`badge ${acc.mode === 'api' ? 'badge-amber' : 'badge-low'}`}>
                              {acc.mode === 'api' ? 'API Posting' : 'Manual Copy'}
                            </span>
                          </div>
                          {acc.focus && acc.focus.length > 0 && (
                            <div style={{ marginTop: 'var(--sp-1)', fontSize: 'var(--fs-xs)', color: 'var(--text-subtle)' }}>
                              Focus: <strong>{acc.focus.join(', ')}</strong>
                            </div>
                          )}
                        </div>

                        <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => {
                              if (isEditingVoice) {
                                setEditingVoiceAccount(null);
                              } else {
                                setEditingVoiceAccount(`${acc.platform}:${acc.handle}`);
                                setVoiceSampleText((acc.voice_samples || []).join('\n---\n'));
                              }
                            }}
                          >
                            <Volume2 size={13} />
                            <span>Voice Samples ({acc.voice_samples_count})</span>
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => handleUnlinkAccount(acc.platform, acc.handle)}
                            title="Unlink this account"
                            style={{ color: 'var(--danger-text)' }}
                          >
                            <Trash2 size={13} />
                          </button>
                        </div>
                      </div>

                      {/* Health & Cap Summary */}
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                          gap: 'var(--sp-3)',
                          background: 'var(--surface-subtle)',
                          padding: 'var(--sp-3)',
                          borderRadius: 'var(--r-md)',
                          border: '1px solid var(--border)',
                          marginBottom: 'var(--sp-3)',
                          fontSize: 'var(--fs-xs)',
                        }}
                      >
                        <div>
                          <span style={{ color: 'var(--text-subtle)' }}>Health Stage: </span>
                          <strong style={{ color: acc.health.stage >= 2 ? 'var(--success-text)' : 'var(--text-main)' }}>
                            {healthStageLabels[acc.health.stage] || `Stage ${acc.health.stage}`}
                          </strong>
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-subtle)' }}>Suggested Daily Cap: </span>
                          <strong>{acc.health.suggested_daily_cap} posts/day</strong>
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-subtle)' }}>Max Pitch Level: </span>
                          <strong>Level {acc.health.max_pitch_level}</strong>
                        </div>
                        <div>
                          <span style={{ color: 'var(--text-subtle)' }}>API Ready: </span>
                          <strong>{acc.credentials.ready ? '✅ Yes' : '⚠️ Manual'}</strong>
                        </div>
                      </div>

                      {/* Health Reasons */}
                      {acc.health.reasons && acc.health.reasons.length > 0 && (
                        <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', marginBottom: 'var(--sp-3)' }}>
                          <strong>Account Audit: </strong>
                          {acc.health.reasons.join(' · ')}
                        </div>
                      )}

                      {/* Credentials Status Checklist */}
                      {acc.credentials.variables && acc.credentials.variables.length > 0 && (
                        <div style={{ marginTop: 'var(--sp-2)', fontSize: 'var(--fs-xs)' }}>
                          <span style={{ fontWeight: 600, color: 'var(--text-subtle)' }}>Environment Credentials Checklist:</span>
                          <div style={{ display: 'flex', gap: 'var(--sp-2)', flexWrap: 'wrap', marginTop: 'var(--sp-1)' }}>
                            {acc.credentials.variables.map((v) => (
                              <span
                                key={v.name}
                                className={`badge ${v.set ? 'badge-high' : 'badge-low'}`}
                                style={{ fontSize: '11px' }}
                                title={v.also_read ? `Also reads fallback: ${v.also_read}` : undefined}
                              >
                                {v.set ? <Check size={11} style={{ display: 'inline', marginRight: '3px' }} /> : <X size={11} style={{ display: 'inline', marginRight: '3px' }} />}
                                {v.name}
                              </span>
                            ))}
                          </div>
                          {acc.credentials.note && (
                            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
                              {acc.credentials.note}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Expandable Voice Samples Editor */}
                      {isEditingVoice && (
                        <div style={{ marginTop: 'var(--sp-4)', paddingTop: 'var(--sp-4)', borderTop: '1px solid var(--border)' }}>
                          <h4 style={{ fontSize: 'var(--fs-sm)', fontWeight: 600, marginBottom: 'var(--sp-1)' }}>
                            Voice & Writing Style Samples for @{acc.handle}
                          </h4>
                          <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', marginBottom: 'var(--sp-2)' }}>
                            Paste 3–5 real comments or posts you authored. Separate multiple examples with <code>---</code> on its own line. Reply drafts for this account will mimic your natural pacing and cadence.
                          </p>
                          <textarea
                            className="textarea"
                            rows={5}
                            placeholder="Example 1: I ran into that exact caching bug last year. We ended up switching to WAL mode in SQLite and it completely stopped WAL lock contention.&#10;---&#10;Example 2: In my experience, reaching out directly with value first always beats generic pitch emails."
                            value={voiceSampleText}
                            onChange={(e) => setVoiceSampleText(e.target.value)}
                          />
                          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--sp-2)', marginTop: 'var(--sp-2)' }}>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => setEditingVoiceAccount(null)}
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              onClick={() => handleSaveVoice(acc.platform, acc.handle)}
                            >
                              <Save size={13} />
                              <span>Save Voice Samples</span>
                            </button>
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
      )}

      {/* ── TAB 2: CONNECTIONS GUIDE ── */}
      {activeTab === 'connections' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-6)' }}>
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>Platform Connections & API Guide</h2>
                <p>
                  Review the exact connectivity requirements, quotas, and environment variable names for every search engine and discussion community.
                </p>
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={loadConnections}
                disabled={loadingConnections}
              >
                <RefreshCw size={13} className={loadingConnections ? 'spin' : ''} />
                <span>Refresh Status</span>
              </button>
            </div>

            {loadingConnections || !connectionsGuide ? (
              <div style={{ padding: 'var(--sp-8)', textAlign: 'center', color: 'var(--text-muted)' }}>
                Loading connections guide…
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
                <div className="notice notice-info">
                  <Info size={16} />
                  <div>
                    <strong>Where variables live:</strong> {connectionsGuide.where_to_set_variables}
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 'var(--sp-4)' }}>
                  {connectionsGuide.sources.map((src) => {
                    const isReady = src.status === 'ready';
                    return (
                      <div key={src.source} className="card" style={{ padding: 'var(--sp-5)' }}>
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                            marginBottom: 'var(--sp-2)',
                          }}
                        >
                          <h3 style={{ fontSize: 'var(--fs-base)', fontWeight: 700, margin: 0 }}>
                            {src.name}
                          </h3>
                          <span className={`badge ${isReady ? 'badge-high' : 'badge-amber'}`}>
                            {isReady ? 'Ready' : 'Partial Setup'}
                          </span>
                        </div>

                        <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', marginBottom: 'var(--sp-3)' }}>
                          <strong>Default: </strong>{src.works_without_setup}
                        </div>

                        {/* Read Variables */}
                        {src.read_variables && src.read_variables.length > 0 && (
                          <div style={{ marginBottom: 'var(--sp-3)' }}>
                            <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--text-subtle)', marginBottom: '4px' }}>
                              Variables:
                            </div>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                              {src.read_variables.map((v) => (
                                <div
                                  key={v.name}
                                  style={{
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                    alignItems: 'center',
                                    fontSize: '11px',
                                    background: 'var(--surface-subtle)',
                                    padding: '3px 8px',
                                    borderRadius: '4px',
                                  }}
                                >
                                  <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{v.name}</span>
                                  <span className={`badge ${v.set ? 'badge-high' : 'badge-low'}`} style={{ fontSize: '10px' }}>
                                    {v.set ? 'Set' : 'Missing'}
                                  </span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Python Packages (e.g. youtube_transcript_api) */}
                        {src.packages && src.packages.length > 0 && (
                          <div style={{ marginBottom: 'var(--sp-3)' }}>
                            <div style={{ fontSize: 'var(--fs-xs)', fontWeight: 600, color: 'var(--text-subtle)', marginBottom: '4px' }}>
                              Optional Packages:
                            </div>
                            {src.packages.map((pkg) => (
                              <div
                                key={pkg.import}
                                style={{
                                  fontSize: '11px',
                                  background: 'var(--surface-subtle)',
                                  padding: '4px 8px',
                                  borderRadius: '4px',
                                  marginBottom: '4px',
                                }}
                              >
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <code style={{ fontSize: '11px' }}>{pkg.install}</code>
                                  <span className={`badge ${pkg.installed ? 'badge-high' : 'badge-amber'}`} style={{ fontSize: '10px' }}>
                                    {pkg.installed ? 'Installed' : 'Not installed'}
                                  </span>
                                </div>
                                <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>{pkg.purpose}</div>
                              </div>
                            ))}
                          </div>
                        )}

                        {/* Posting details */}
                        <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-subtle)', marginBottom: 'var(--sp-2)' }}>
                          <strong>Posting: </strong>{src.posting}
                        </div>

                        {/* Quotas & limits */}
                        {src.limits && (
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            <strong>Limits: </strong>{src.limits}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </section>
        </div>
      )}

      {/* ── TAB 3: THREAD RULES & SAFETY ── */}
      {activeTab === 'safety' && (
        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-6)' }}>
          {/* Master Emergency Stop Switch */}
          <section
            className="card"
            style={{
              padding: 'var(--sp-5)',
              background: postingSettings.emergency_stop ? 'var(--danger-bg)' : 'var(--surface)',
              borderColor: postingSettings.emergency_stop ? 'var(--danger-border)' : 'var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 'var(--sp-4)',
              flexWrap: 'wrap',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
              <ShieldAlert size={28} color={postingSettings.emergency_stop ? 'var(--danger)' : 'var(--text-subtle)'} />
              <div>
                <div
                  style={{
                    fontWeight: 700,
                    fontSize: 'var(--fs-base)',
                    color: postingSettings.emergency_stop ? 'var(--danger-text)' : 'var(--text-main)',
                  }}
                >
                  Master Emergency Stop
                </div>
                <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', marginTop: '2px' }}>
                  Instantly halts and locks all community discovery, reply drafting, and posting operations across the system.
                </div>
              </div>
            </div>

            <label
              htmlFor="emergency-stop-toggle"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 'var(--sp-2)',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 'var(--fs-sm)',
              }}
            >
              <input
                id="emergency-stop-toggle"
                type="checkbox"
                checked={postingSettings.emergency_stop}
                onChange={(e) => setPostingSettings({ ...postingSettings, emergency_stop: e.target.checked })}
                style={{ width: '20px', height: '20px', cursor: 'pointer' }}
              />
              <span style={{ color: postingSettings.emergency_stop ? 'var(--danger-text)' : 'var(--text-main)' }}>
                {postingSettings.emergency_stop ? 'STOP ACTIVE (HALTED)' : 'Normal Active Operation'}
              </span>
            </label>
          </section>

          {/* New Thread Engagement Safety Rules (v3.4.0) */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                  <ShieldCheck size={18} style={{ color: 'var(--primary)' }} />
                  <h2>Thread Safety & Multi-Reply Coordination (v3.4.0)</h2>
                </div>
                <p>
                  Coordinate replies when participating more than once in a discussion. Protects accounts from looking coordinated or trigger-spamming platforms.
                </p>
              </div>
            </div>

            <div className="form-grid-3" style={{ marginBottom: 'var(--sp-4)' }}>
              <div className="form-group">
                <label htmlFor="settings-max-thread-replies" className="label">
                  Max Replies Per Thread (1–3)
                </label>
                <select
                  id="settings-max-thread-replies"
                  className="select"
                  value={postingSettings.max_replies_per_thread ?? 2}
                  onChange={(e) =>
                    setPostingSettings({
                      ...postingSettings,
                      max_replies_per_thread: parseInt(e.target.value, 10) || 2,
                    })
                  }
                >
                  <option value="1">1 Reply (Conservative single-touch)</option>
                  <option value="2">2 Replies (Default: distinct targets & openings)</option>
                  <option value="3">3 Replies (Maximum allowed ceiling)</option>
                </select>
                <span className="helper-text">
                  Enforced at draft and publishing: 1 account per thread, distinct openings, max 1 product mention.
                </span>
              </div>

              <div className="form-group">
                <label htmlFor="settings-min-thread-gap" className="label">
                  Min Thread Gap (Minutes)
                </label>
                <input
                  id="settings-min-thread-gap"
                  type="number"
                  className="input"
                  min={0}
                  max={360}
                  step={15}
                  value={postingSettings.min_thread_gap_minutes ?? 60}
                  onChange={(e) =>
                    setPostingSettings({
                      ...postingSettings,
                      min_thread_gap_minutes: parseInt(e.target.value, 10) || 0,
                    })
                  }
                />
                <span className="helper-text">
                  Minimum wait between two replies in the same thread (default: 60 minutes).
                </span>
              </div>

              <div className="form-group">
                <label htmlFor="settings-community-gap-days" className="label">
                  Community Overlap Gap (Days)
                </label>
                <input
                  id="settings-community-gap-days"
                  type="number"
                  className="input"
                  min={0}
                  max={60}
                  value={postingSettings.product_community_gap_days ?? 7}
                  onChange={(e) =>
                    setPostingSettings({
                      ...postingSettings,
                      product_community_gap_days: parseInt(e.target.value, 10) || 0,
                    })
                  }
                />
                <span className="helper-text">
                  When one account mentions the product in a community, other accounts stay out for this many days (gate: community_overlap).
                </span>
              </div>
            </div>
          </section>

          {/* Publishing Controls & Anti-Spam */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>General Publishing Controls & Limits</h2>
                <p>Enforce strict daily caps, randomized jitter, and promotional ratio limits.</p>
              </div>
            </div>

            <div className="form-grid-3" style={{ marginBottom: 'var(--sp-4)' }}>
              <div className="form-group">
                <label htmlFor="settings-post-mode" className="label">
                  Publishing Mode
                </label>
                <select
                  id="settings-post-mode"
                  className="select"
                  value={postingSettings.mode}
                  onChange={(e) =>
                    setPostingSettings({ ...postingSettings, mode: e.target.value as any })
                  }
                >
                  <option value="draft">Draft Mode Only (Read & Copy Only)</option>
                  <option value="manual">Manual Approval (Recommended Default)</option>
                  <option value="automatic">Controlled Automatic Posting (API)</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="settings-daily-limit" className="label">
                  Global Daily Limit
                </label>
                <input
                  id="settings-daily-limit"
                  type="number"
                  className="input"
                  min={1}
                  max={50}
                  value={postingSettings.daily_limit}
                  onChange={(e) =>
                    setPostingSettings({
                      ...postingSettings,
                      daily_limit: parseInt(e.target.value, 10) || 5,
                    })
                  }
                />
              </div>

              <div className="form-group">
                <label htmlFor="settings-min-interval" className="label">
                  Minimum Platform Interval (Seconds)
                </label>
                <input
                  id="settings-min-interval"
                  type="number"
                  className="input"
                  min={60}
                  step={60}
                  value={postingSettings.min_interval_seconds}
                  onChange={(e) =>
                    setPostingSettings({
                      ...postingSettings,
                      min_interval_seconds: parseInt(e.target.value, 10) || 600,
                    })
                  }
                />
              </div>
            </div>

            <div className="form-grid-2" style={{ marginBottom: 'var(--sp-4)' }}>
              <div className="form-group">
                <label htmlFor="settings-interval-jitter" className="label">
                  Interval Jitter Fraction ({Math.round((postingSettings.interval_jitter ?? 0.3) * 100)}%)
                </label>
                <input
                  id="settings-interval-jitter"
                  type="range"
                  min="0"
                  max="0.5"
                  step="0.05"
                  value={postingSettings.interval_jitter ?? 0.3}
                  onChange={(e) =>
                    setPostingSettings({
                      ...postingSettings,
                      interval_jitter: parseFloat(e.target.value),
                    })
                  }
                  style={{ width: '100%', cursor: 'pointer' }}
                />
                <span className="helper-text">
                  Adds random delay on top of minimum interval to prevent bot-detection heuristics.
                </span>
              </div>

              <div className="form-group">
                <label htmlFor="settings-max-mention" className="label">
                  Max Mention Ratio ({Math.round((postingSettings.max_mention_ratio ?? 0.1) * 100)}%)
                </label>
                <input
                  id="settings-max-mention"
                  type="range"
                  min="0.05"
                  max="0.3"
                  step="0.05"
                  value={postingSettings.max_mention_ratio ?? 0.1}
                  onChange={(e) =>
                    setPostingSettings({
                      ...postingSettings,
                      max_mention_ratio: parseFloat(e.target.value),
                    })
                  }
                  style={{ width: '100%', cursor: 'pointer' }}
                />
                <span className="helper-text">
                  Safety ceiling: at most this fraction of recent comments may name the product (default: 10%).
                </span>
              </div>
            </div>

            <div className="form-grid-2" style={{ marginBottom: 'var(--sp-4)' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', cursor: 'pointer', fontSize: 'var(--fs-sm)', fontWeight: 500 }}>
                <input
                  type="checkbox"
                  checked={postingSettings.require_account_health ?? true}
                  onChange={(e) =>
                    setPostingSettings({ ...postingSettings, require_account_health: e.target.checked })
                  }
                  style={{ width: '16px', height: '16px' }}
                />
                <span>Enforce account health requirements before allowing product-aware replies</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)', cursor: 'pointer', fontSize: 'var(--fs-sm)', fontWeight: 500 }}>
                <input
                  type="checkbox"
                  checked={postingSettings.require_rules_ack ?? true}
                  onChange={(e) =>
                    setPostingSettings({ ...postingSettings, require_rules_ack: e.target.checked })
                  }
                  style={{ width: '16px', height: '16px' }}
                />
                <span>Require recorded community rules acknowledgement before publishing</span>
              </label>
            </div>

            <div className="form-group">
              <label htmlFor="settings-allowed-communities" className="label">
                Allowed Communities Whitelist (Comma-separated)
              </label>
              <input
                id="settings-allowed-communities"
                type="text"
                className="input"
                placeholder="Leave empty for all communities, or specify whitelist e.g. r/startups, r/SaaS"
                value={postingSettings.allowed_communities.join(', ')}
                onChange={(e) =>
                  setPostingSettings({
                    ...postingSettings,
                    allowed_communities: e.target.value.split(',').map((x) => x.trim()).filter(Boolean),
                  })
                }
              />
            </div>
          </section>

          {/* Save Button */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--sp-2)' }}>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              <Save size={16} />
              <span>{saving ? 'Saving Changes…' : 'Save Safety Settings'}</span>
            </button>
          </div>
        </form>
      )}

      {/* ── TAB 4: AI & STORAGE CONFIG ── */}
      {activeTab === 'ai_storage' && (
        <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-6)' }}>
          {/* AI Provider Configuration */}
          <section className="panel">
            <div className="panel-header" style={{ flexWrap: 'wrap', gap: 'var(--sp-2)' }}>
              <div>
                <h2>AI Model Provider</h2>
                <p>Configure which LLM powers profile extraction, search query planning, and personalized reply generation.</p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                {llmSettings.configured ? (
                  <span className="badge badge-high" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <CheckCircle2 size={13} />
                    AI Ready & Configured
                  </span>
                ) : (
                  <span className="badge badge-amber" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                    <AlertTriangle size={13} />
                    API Key Required
                  </span>
                )}
              </div>
            </div>

            <div className="form-grid-2" style={{ marginBottom: 'var(--sp-4)' }}>
              <div className="form-group">
                <label htmlFor="settings-llm-provider" className="label">
                  LLM Provider
                </label>
                <select
                  id="settings-llm-provider"
                  className="select"
                  value={llmSettings.provider}
                  onChange={(e) => {
                    const p = e.target.value;
                    const defaultModels: Record<string, string> = {
                      gemini: 'gemini-2.5-flash',
                      openai: 'gpt-4o-mini',
                      anthropic: 'claude-3-5-haiku-20241022',
                      groq: 'llama-3.3-70b-versatile',
                      deepseek: 'deepseek-chat',
                    };
                    setLlmSettings({
                      ...llmSettings,
                      provider: p,
                      model: defaultModels[p] || llmSettings.model,
                    });
                  }}
                >
                  <option value="gemini">Google Gemini</option>
                  <option value="openai">OpenAI</option>
                  <option value="anthropic">Anthropic Claude</option>
                  <option value="groq">Groq (Ultra-Fast)</option>
                  <option value="deepseek">DeepSeek</option>
                </select>
              </div>

              <div className="form-group">
                <label htmlFor="settings-llm-model" className="label">
                  Model Identifier
                </label>
                <input
                  id="settings-llm-model"
                  type="text"
                  className="input"
                  value={llmSettings.model}
                  onChange={(e) => setLlmSettings({ ...llmSettings, model: e.target.value })}
                />
              </div>
            </div>

            <div className="form-group">
              <label htmlFor="settings-llm-api-key" className="label">
                API Key for {llmSettings.provider}
                {llmSettings.has_api_key && (
                  <span style={{ color: 'var(--success)', fontWeight: 600, marginLeft: '8px' }}>
                    ✓ Key Saved in Private Config
                  </span>
                )}
              </label>
              <input
                id="settings-llm-api-key"
                type="password"
                className="input"
                placeholder={
                  llmSettings.has_api_key
                    ? '•••••••••••••••• (Leave blank to keep current key)'
                    : `Enter ${llmSettings.provider} API key`
                }
                value={llmSettings.api_key || ''}
                onChange={(e) => setLlmSettings({ ...llmSettings, api_key: e.target.value })}
              />
              <span className="helper-text">
                Saved only in private <code>~/.agent-reach/config.yaml</code> with 0600 permissions. Never stored in SQLite.
              </span>
            </div>
          </section>

          {/* Model Context Protocol (MCP) Settings */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                  <Cpu size={18} style={{ color: 'var(--primary)' }} />
                  <h2>Model Context Protocol (MCP) & Host AI Controls</h2>
                </div>
                <p>Configure how AgentReach connects to IDEs and agents (Cursor, Claude Code, Antigravity, VS Code).</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 'var(--sp-4)' }}>
                <div className="form-group">
                  <label htmlFor="settings-mcp-output-format" className="label">
                    Default Export Format
                  </label>
                  <select
                    id="settings-mcp-output-format"
                    className="select"
                    value={mcpSettings.default_output_format}
                    onChange={(e) =>
                      setMcpSettings({
                        ...mcpSettings,
                        default_output_format: e.target.value as any,
                      })
                    }
                  >
                    <option value="both">Both Markdown & JSON (.md + .json)</option>
                    <option value="markdown">Markdown Report (.md)</option>
                    <option value="json">Structured JSON (.json)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label htmlFor="settings-mcp-min-score" className="label">
                    Default Lead Score Threshold (0–100)
                  </label>
                  <input
                    id="settings-mcp-min-score"
                    type="number"
                    min={0}
                    max={100}
                    className="input"
                    value={mcpSettings.default_min_score}
                    onChange={(e) =>
                      setMcpSettings({
                        ...mcpSettings,
                        default_min_score: Math.max(0, Math.min(100, parseInt(e.target.value, 10) || 0)),
                      })
                    }
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="settings-mcp-export-path" className="label">
                    Default Export Directory
                  </label>
                  <input
                    id="settings-mcp-export-path"
                    type="text"
                    className="input"
                    value={mcpSettings.default_export_path}
                    onChange={(e) => setMcpSettings({ ...mcpSettings, default_export_path: e.target.value })}
                  />
                </div>
              </div>
            </div>
          </section>

          {/* Database & Verification Engine Optimization */}
          <section className="panel">
            <div className="panel-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                <Database size={18} style={{ color: 'var(--primary)' }} />
                <h2>Storage & Verification Engine Optimization</h2>
              </div>
              <p>Fine-tune SQLite connection pooling, sync modes, and autonomous auditor verification settings.</p>
            </div>

            <div className="form-grid-2">
              <div className="form-group">
                <label htmlFor="settings-db-sync" className="label">
                  SQLite Sync Mode (AGENT_REACH_DB_SYNC)
                </label>
                <select
                  id="settings-db-sync"
                  className="select"
                  value={dbSyncMode}
                  onChange={(e) => setDbSyncMode(e.target.value as any)}
                >
                  <option value="NORMAL">NORMAL (Recommended: 3x faster writes, standard crash safety)</option>
                  <option value="EXTRA">EXTRA (Maximum durability on every write transaction)</option>
                  <option value="OFF">OFF (Asynchronous writes for high-throughput testing)</option>
                </select>
                <span className="helper-text">
                  Cached idle connections drop write latencies from 1.26ms to 0.37ms.
                </span>
              </div>

              <div className="form-group">
                <label htmlFor="settings-auditor-provider" className="label">
                  Autonomous Auditor Provider (Optional)
                </label>
                <input
                  id="settings-auditor-provider"
                  type="text"
                  className="input"
                  placeholder="e.g. openai, groq, anthropic"
                  value={auditorProvider}
                  onChange={(e) => setAuditorProvider(e.target.value)}
                />
                <span className="helper-text">
                  Independent model to run canary claim verification and anti-hallucination audits.
                </span>
              </div>

              <div className="form-group">
                <label htmlFor="settings-auditor-model" className="label">
                  Autonomous Auditor Model Name (Optional)
                </label>
                <input
                  id="settings-auditor-model"
                  type="text"
                  className="input"
                  placeholder="e.g. gpt-4o-mini, llama-3.3-70b-versatile"
                  value={auditorModel}
                  onChange={(e) => setAuditorModel(e.target.value)}
                />
                <span className="helper-text">
                  Specific model name for secondary verifier checks.
                </span>
              </div>
            </div>
          </section>

          {/* Save Button */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 'var(--sp-2)' }}>
            <button type="submit" className="btn btn-primary" disabled={saving}>
              <Save size={16} />
              <span>{saving ? 'Saving Changes…' : 'Save AI & Storage Settings'}</span>
            </button>
          </div>
        </form>
      )}

      {/* ── TAB: AI CLIENTS & MCP INTEGRATION ── */}
      {activeTab === 'mcp_ai' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-6)' }}>
          {/* Header Card */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h2>Model Context Protocol (MCP) & AI Clients</h2>
                <p>
                  Connect Claude Desktop, Claude Code, Cursor, Windsurf, or Claude Web directly to Agent Reach.
                  Tools share the exact same database, business profile, and verifiers.
                </p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="badge badge-success">
                  <CheckCircle2 size={12} style={{ display: 'inline', marginRight: '4px' }} />
                  MCP Server Active
                </span>
                <span className="badge badge-secondary">Transports: Stdio, SSE, HTTP</span>
              </div>
            </div>

            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                gap: 'var(--sp-4)',
                marginTop: 'var(--sp-4)',
              }}
            >
              <div
                className="card"
                style={{
                  padding: 'var(--sp-4)',
                  background: 'var(--surface-subtle)',
                  borderRadius: 'var(--r-md)',
                }}
              >
                <strong style={{ display: 'block', marginBottom: '4px', fontSize: 'var(--fs-sm)' }}>
                  Local Stdio Endpoint
                </strong>
                <code
                  style={{
                    fontSize: 'var(--fs-xs)',
                    background: 'var(--surface)',
                    padding: '4px 8px',
                    borderRadius: 'var(--r-xs)',
                    display: 'block',
                  }}
                >
                  agent-reach mcp
                </code>
                <span
                  style={{
                    fontSize: 'var(--fs-xs)',
                    color: 'var(--text-subtle)',
                    marginTop: '6px',
                    display: 'block',
                  }}
                >
                  For Claude Desktop, Cursor, and terminal CLI clients.
                </span>
              </div>

              <div
                className="card"
                style={{
                  padding: 'var(--sp-4)',
                  background: 'var(--surface-subtle)',
                  borderRadius: 'var(--r-md)',
                }}
              >
                <strong style={{ display: 'block', marginBottom: '4px', fontSize: 'var(--fs-sm)' }}>
                  Integrated Remote SSE Endpoint
                </strong>
                <code
                  style={{
                    fontSize: 'var(--fs-xs)',
                    background: 'var(--surface)',
                    padding: '4px 8px',
                    borderRadius: 'var(--r-xs)',
                    display: 'block',
                  }}
                >
                  http://127.0.0.1:8000/mcp/sse
                </code>
                <span
                  style={{
                    fontSize: 'var(--fs-xs)',
                    color: 'var(--text-subtle)',
                    marginTop: '6px',
                    display: 'block',
                  }}
                >
                  For Claude Web and remote network clients (with AGENT_REACH_API_KEY).
                </span>
              </div>
            </div>
          </section>

          {/* Client Setup Cards */}
          <section className="panel">
            <div className="panel-header">
              <div>
                <h3>Client Configuration Guides</h3>
                <p>Select your client below and paste the generated snippet into its configuration.</p>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)', marginTop: 'var(--sp-4)' }}>
              {/* Claude Desktop */}
              <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 'var(--sp-4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-2)' }}>
                  <div>
                    <strong style={{ fontSize: 'var(--fs-base)' }}>Claude Desktop</strong>
                    <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-subtle)', marginLeft: '8px' }}>
                      Add to %APPDATA%\Claude\claude_desktop_config.json
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() =>
                      copyToClipboard(
                        JSON.stringify(
                          {
                            mcpServers: {
                              'agent-reach': {
                                command: 'agent-reach',
                                args: ['mcp'],
                              },
                            },
                          },
                          null,
                          2
                        ),
                        'claude-desktop'
                      )
                    }
                  >
                    {copiedSnippet === 'claude-desktop' ? <Check size={14} /> : <Copy size={14} />}
                    <span>{copiedSnippet === 'claude-desktop' ? 'Copied!' : 'Copy Config'}</span>
                  </button>
                </div>
                <pre style={{ background: 'var(--surface-subtle)', padding: 'var(--sp-3)', borderRadius: 'var(--r-sm)', fontSize: 'var(--fs-xs)', overflowX: 'auto' }}>
{`{
  "mcpServers": {
    "agent-reach": {
      "command": "agent-reach",
      "args": ["mcp"]
    }
  }
}`}
                </pre>
              </div>

              {/* Claude Code CLI */}
              <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 'var(--sp-4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-2)' }}>
                  <div>
                    <strong style={{ fontSize: 'var(--fs-base)' }}>Claude Code (CLI)</strong>
                    <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-subtle)', marginLeft: '8px' }}>
                      Run in your terminal to register the tool suite
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() =>
                      copyToClipboard('claude mcp add agent-reach -- agent-reach mcp', 'claude-code')
                    }
                  >
                    {copiedSnippet === 'claude-code' ? <Check size={14} /> : <Copy size={14} />}
                    <span>{copiedSnippet === 'claude-code' ? 'Copied!' : 'Copy Command'}</span>
                  </button>
                </div>
                <pre style={{ background: 'var(--surface-subtle)', padding: 'var(--sp-3)', borderRadius: 'var(--r-sm)', fontSize: 'var(--fs-xs)', overflowX: 'auto' }}>
claude mcp add agent-reach -- agent-reach mcp
                </pre>
              </div>

              {/* Cursor / Windsurf */}
              <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 'var(--sp-4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-2)' }}>
                  <div>
                    <strong style={{ fontSize: 'var(--fs-base)' }}>Cursor & Windsurf</strong>
                    <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-subtle)', marginLeft: '8px' }}>
                      Add to .cursor/mcp.json or Windsurf MCP Settings
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() =>
                      copyToClipboard(
                        JSON.stringify(
                          {
                            mcpServers: {
                              'agent-reach': {
                                command: 'agent-reach',
                                args: ['mcp'],
                              },
                            },
                          },
                          null,
                          2
                        ),
                        'cursor'
                      )
                    }
                  >
                    {copiedSnippet === 'cursor' ? <Check size={14} /> : <Copy size={14} />}
                    <span>{copiedSnippet === 'cursor' ? 'Copied!' : 'Copy Config'}</span>
                  </button>
                </div>
                <pre style={{ background: 'var(--surface-subtle)', padding: 'var(--sp-3)', borderRadius: 'var(--r-sm)', fontSize: 'var(--fs-xs)', overflowX: 'auto' }}>
{`{
  "mcpServers": {
    "agent-reach": {
      "command": "agent-reach",
      "args": ["mcp"]
    }
  }
}`}
                </pre>
              </div>

              {/* Claude Web (Remote MCP) */}
              <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 'var(--sp-4)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 'var(--sp-2)' }}>
                  <div>
                    <strong style={{ fontSize: 'var(--fs-base)' }}>Claude Web (Remote MCP Server)</strong>
                    <span style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-subtle)', marginLeft: '8px' }}>
                      Connect over HTTP/SSE with bearer token authorization
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() =>
                      copyToClipboard(
                        JSON.stringify(
                          {
                            mcpServers: {
                              'agent-reach-remote': {
                                url: `http://127.0.0.1:8000/mcp/sse`,
                                transport: 'sse',
                              },
                            },
                          },
                          null,
                          2
                        ),
                        'claude-web'
                      )
                    }
                  >
                    {copiedSnippet === 'claude-web' ? <Check size={14} /> : <Copy size={14} />}
                    <span>{copiedSnippet === 'claude-web' ? 'Copied!' : 'Copy Remote Config'}</span>
                  </button>
                </div>
                <pre style={{ background: 'var(--surface-subtle)', padding: 'var(--sp-3)', borderRadius: 'var(--r-sm)', fontSize: 'var(--fs-xs)', overflowX: 'auto' }}>
{`{
  "mcpServers": {
    "agent-reach-remote": {
      "url": "http://127.0.0.1:8000/mcp/sse",
      "transport": "sse"
    }
  }
}`}
                </pre>
              </div>
            </div>
          </section>
        </div>
      )}

      {/* ── TAB 5: DATA EXPORT ── */}
      {activeTab === 'export' && (
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2>Data Export & Intelligence Backup</h2>
              <p>Download discovered customer leads, qualification scores, and discussion links for CRM import or spreadsheet analysis.</p>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
            <a href={api.getExportUrl('csv', 0)} className="btn btn-secondary" download>
              <Download size={14} />
              <span>Export Qualified Leads (CSV)</span>
            </a>
            <a href={api.getExportUrl('json', 0)} className="btn btn-secondary" download>
              <Download size={14} />
              <span>Export Full Intelligence Dataset (JSON)</span>
            </a>
          </div>
        </section>
      )}
    </div>
  );
};

export default SettingsView;
