import React, { useState, useEffect } from 'react';
import {
  Globe,
  FileText,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Target,
  Save,
  ShieldCheck,
  Sparkles,
  Layers,
  Search,
  UserX,
} from 'lucide-react';
import type { BusinessProfile } from '../types';
import { api } from '../api';

interface ProfileViewProps {
  profile: BusinessProfile | null;
  onProfileUpdated: (profile: BusinessProfile) => void;
}

export const ProfileView: React.FC<ProfileViewProps> = ({ profile, onProfileUpdated }) => {
  const [activeInputMode, setActiveInputMode] = useState<'url' | 'manual'>('url');
  const [urlInput, setUrlInput] = useState('');
  const [nameInput, setNameInput] = useState('');
  const [descInput, setDescInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'info' | 'error' | 'success'; message: string } | null>(null);
  const [activeTab, setActiveTab] = useState<'core' | 'icp' | 'pain' | 'facts' | 'inferences'>('core');

  // Form edit state
  const [formData, setFormData] = useState<Partial<BusinessProfile>>({});

  useEffect(() => {
    if (profile) {
      setFormData({
        ...profile,
        features: profile.features || [],
        problems_solved: profile.problems_solved || [],
        customer_outcomes: profile.customer_outcomes || [],
        target_industries: profile.target_industries || [],
        target_roles: profile.target_roles || [],
        customer_demographics: profile.customer_demographics || [],
        customer_frustrations: profile.customer_frustrations || [],
        competitors_and_alternatives: profile.competitors_and_alternatives || [],
        unique_selling_points: profile.unique_selling_points || [],
        trigger_events: profile.trigger_events || [],
        pain_vocabulary: profile.pain_vocabulary || [],
        not_for: profile.not_for || [],
        facts: profile.facts || [],
        inferences: profile.inferences || [],
      });
    }
  }, [profile]);

  const handleExtractUrl = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!urlInput.trim()) return;
    setLoading(true);
    setFeedback(null);
    try {
      const extracted = await api.extractFromUrl(urlInput.trim());
      onProfileUpdated(extracted);
      setFeedback({
        type: 'success',
        message: 'Profile successfully extracted from website. Review extracted facts and parameters before confirming.',
      });
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Website extraction failed. Please check the URL.',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleExtractManual = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!descInput.trim()) return;
    setLoading(true);
    setFeedback(null);
    try {
      const extracted = await api.extractFromManual(nameInput.trim(), descInput.trim());
      onProfileUpdated(extracted);
      setFeedback({
        type: 'success',
        message: 'Profile synthesized from description. Review the ICP and pain vocabulary below before confirming.',
      });
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Analysis failed. Please check your product description.',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleSaveProfile = async () => {
    if (!formData) return;
    setLoading(true);
    try {
      const updated = await api.updateProfile(formData as BusinessProfile);
      onProfileUpdated(updated);
      setFeedback({
        type: 'success',
        message: 'Business profile saved successfully.',
      });
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Save failed. Please check your inputs.',
      });
    } finally {
      setLoading(false);
    }
  };

  const handleCreateEmptyProfile = () => {
    const empty: BusinessProfile = {
      id: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now()),
      name: nameInput.trim() || 'New Business Profile',
      url: urlInput.trim() || undefined,
      description: descInput.trim() || '',
      industry: '',
      niche: '',
      main_product_or_service: '',
      features: [],
      problems_solved: [],
      customer_outcomes: [],
      icp: '',
      target_industries: [],
      target_roles: [],
      customer_demographics: [],
      customer_frustrations: [],
      competitors_and_alternatives: [],
      unique_selling_points: [],
      pricing_info: '',
      geographic_market: 'Global',
      trigger_events: [],
      pain_vocabulary: [],
      not_for: [],
      facts: [],
      inferences: [],
      confirmed: false,
      created_at: Date.now() / 1000,
      updated_at: Date.now() / 1000,
    };
    setFormData(empty);
    onProfileUpdated(empty);
  };

  const handleConfirmProfile = async () => {
    setLoading(true);
    try {
      const confirmed = await api.confirmProfile();
      onProfileUpdated(confirmed);
      setFeedback({
        type: 'success',
        message: 'Business profile confirmed! Autonomous discovery campaigns are now unlocked.',
      });
    } catch (err: any) {
      setFeedback({
        type: 'error',
        message: err instanceof Error ? err.message : 'Confirmation failed. Please try again.',
      });
    } finally {
      setLoading(false);
    }
  };

  // Helper to handle newline-delimited lists
  const handleListChange = (field: keyof BusinessProfile, text: string) => {
    const list = text.split('\n').map((item) => item.trim()).filter(Boolean);
    setFormData((prev) => ({ ...prev, [field]: list }));
  };

  // Helper to handle comma-delimited lists
  const handleCommaListChange = (field: keyof BusinessProfile, text: string) => {
    const list = text.split(',').map((item) => item.trim()).filter(Boolean);
    setFormData((prev) => ({ ...prev, [field]: list }));
  };

  return (
    <div className="page-shell">
      <div className="page-heading">
        <div>
          <h1>Business Profile & ICP</h1>
          <p>
            Define your value proposition, customer pain points, pain search vocabulary, and ideal customer profile (ICP) to drive high-accuracy discovery.
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

      {/* Extraction / Re-crawl Section */}
      <section className="panel" style={{ marginBottom: 'var(--sp-6)' }}>
        <div className="panel-header">
          <div>
            <h2>Extract or Refresh Business Understanding</h2>
            <p>Analyze your live landing page or submit a detailed product overview to detect target audience and buyer frustrations.</p>
          </div>

          <div className="version-toggle-bar" style={{ alignSelf: 'center' }}>
            <button
              type="button"
              className={`version-tab ${activeInputMode === 'url' ? 'active' : ''}`}
              onClick={() => setActiveInputMode('url')}
            >
              <Globe size={13} style={{ display: 'inline', marginRight: '4px' }} />
              Website URL
            </button>
            <button
              type="button"
              className={`version-tab ${activeInputMode === 'manual' ? 'active' : ''}`}
              onClick={() => setActiveInputMode('manual')}
            >
              <FileText size={13} style={{ display: 'inline', marginRight: '4px' }} />
              Manual Description
            </button>
          </div>
        </div>

        {activeInputMode === 'url' ? (
          <form onSubmit={handleExtractUrl} style={{ display: 'flex', gap: 'var(--sp-3)', flexWrap: 'wrap' }}>
            <div style={{ flex: 1, minWidth: '280px' }}>
              <input
                id="profile-url-input"
                aria-label="Website URL"
                type="url"
                className="input"
                placeholder="https://yourproduct.com (crawls features, pricing, and FAQ)"
                value={urlInput}
                onChange={(e) => setUrlInput(e.target.value)}
                disabled={loading}
                required
              />
            </div>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              <Globe size={16} />
              <span>{loading ? 'Analyzing Pages…' : 'Analyze Website'}</span>
            </button>
          </form>
        ) : (
          <form onSubmit={handleExtractManual} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-3)' }}>
            <input
              id="profile-manual-name"
              aria-label="Product or Service Name"
              type="text"
              className="input"
              placeholder="Product or Service Name (optional)"
              value={nameInput}
              onChange={(e) => setNameInput(e.target.value)}
              disabled={loading}
            />
            <textarea
              id="profile-manual-desc"
              aria-label="Product or Service Description"
              className="textarea"
              rows={3}
              placeholder="Describe what your product does, problems it solves, target users, and key differentiators…"
              value={descInput}
              onChange={(e) => setDescInput(e.target.value)}
              disabled={loading}
              required
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleCreateEmptyProfile}
                disabled={loading}
              >
                <span>Or Fill In Manually (No AI)</span>
              </button>
              <button type="submit" className="btn btn-primary" disabled={loading}>
                <FileText size={16} />
                <span>{loading ? 'Synthesizing Profile…' : 'Extract Business Profile'}</span>
              </button>
            </div>
          </form>
        )}
      </section>

      {/* Confirmation & Status Bar */}
      {profile && (
        <section
          className="card"
          style={{
            padding: 'var(--sp-4) var(--sp-5)',
            marginBottom: 'var(--sp-6)',
            background: profile.confirmed ? 'var(--success-bg)' : 'var(--warning-bg)',
            borderColor: profile.confirmed ? 'var(--success-border)' : 'var(--warning-border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 'var(--sp-4)',
            flexWrap: 'wrap',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-3)' }}>
            {profile.confirmed ? (
              <ShieldCheck size={24} color="var(--success)" />
            ) : (
              <AlertTriangle size={24} color="var(--warning)" />
            )}
            <div>
              <div
                style={{
                  fontWeight: 700,
                  fontSize: 'var(--fs-base)',
                  color: profile.confirmed ? 'var(--success-text)' : 'var(--warning-text)',
                }}
              >
                {profile.confirmed
                  ? 'Business Profile Confirmed for Autonomous Discovery'
                  : 'Action Required: Review & Confirm Business Profile'}
              </div>
              <div
                style={{
                  fontSize: 'var(--fs-xs)',
                  color: profile.confirmed ? '#065f46' : '#78350f',
                  marginTop: '2px',
                }}
              >
                {profile.confirmed
                  ? 'Leads Licker uses this ICP model, negative filters, and pain vocabulary to search and score discussions.'
                  : 'Review the extracted ICP parameters, negative filters, and pain terms below, then click Confirm Profile to unlock discovery runs.'}
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 'var(--sp-2)' }}>
            <button className="btn btn-secondary btn-sm" onClick={handleSaveProfile} disabled={loading}>
              <Save size={14} />
              <span>Save Edits</span>
            </button>
            {!profile.confirmed && (
              <button className="btn btn-primary btn-sm" onClick={handleConfirmProfile} disabled={loading}>
                <CheckCircle2 size={14} />
                <span>Confirm Profile</span>
              </button>
            )}
          </div>
        </section>
      )}

      {/* Tabbed Profile Editor */}
      {profile && (
        <div>
          <div
            role="tablist"
            aria-label="Profile Sections"
            style={{
              display: 'flex',
              gap: 'var(--sp-2)',
              borderBottom: '1px solid var(--border)',
              marginBottom: 'var(--sp-5)',
              overflowX: 'auto',
            }}
          >
            <button
              role="tab"
              aria-selected={activeTab === 'core'}
              onClick={() => setActiveTab('core')}
              style={{
                padding: 'var(--sp-2) var(--sp-4)',
                border: 'none',
                background: 'none',
                borderBottom: activeTab === 'core' ? '2px solid var(--primary)' : '2px solid transparent',
                fontWeight: activeTab === 'core' ? 700 : 500,
                color: activeTab === 'core' ? 'var(--primary)' : 'var(--text-muted)',
                cursor: 'pointer',
                fontSize: 'var(--fs-sm)',
                whiteSpace: 'nowrap',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <Layers size={14} />
              <span>Product & Value</span>
            </button>

            <button
              role="tab"
              aria-selected={activeTab === 'icp'}
              onClick={() => setActiveTab('icp')}
              style={{
                padding: 'var(--sp-2) var(--sp-4)',
                border: 'none',
                background: 'none',
                borderBottom: activeTab === 'icp' ? '2px solid var(--primary)' : '2px solid transparent',
                fontWeight: activeTab === 'icp' ? 700 : 500,
                color: activeTab === 'icp' ? 'var(--primary)' : 'var(--text-muted)',
                cursor: 'pointer',
                fontSize: 'var(--fs-sm)',
                whiteSpace: 'nowrap',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <Target size={14} />
              <span>ICP & Guardrails</span>
            </button>

            <button
              role="tab"
              aria-selected={activeTab === 'pain'}
              onClick={() => setActiveTab('pain')}
              style={{
                padding: 'var(--sp-2) var(--sp-4)',
                border: 'none',
                background: 'none',
                borderBottom: activeTab === 'pain' ? '2px solid var(--primary)' : '2px solid transparent',
                fontWeight: activeTab === 'pain' ? 700 : 500,
                color: activeTab === 'pain' ? 'var(--primary)' : 'var(--text-muted)',
                cursor: 'pointer',
                fontSize: 'var(--fs-sm)',
                whiteSpace: 'nowrap',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <Search size={14} />
              <span>Pain & Search Vocabulary</span>
            </button>

            <button
              role="tab"
              aria-selected={activeTab === 'facts'}
              onClick={() => setActiveTab('facts')}
              style={{
                padding: 'var(--sp-2) var(--sp-4)',
                border: 'none',
                background: 'none',
                borderBottom: activeTab === 'facts' ? '2px solid var(--primary)' : '2px solid transparent',
                fontWeight: activeTab === 'facts' ? 700 : 500,
                color: activeTab === 'facts' ? 'var(--primary)' : 'var(--text-muted)',
                cursor: 'pointer',
                fontSize: 'var(--fs-sm)',
                whiteSpace: 'nowrap',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <Globe size={14} />
              <span>Ground Truth Claims ({formData.facts?.length || 0})</span>
            </button>

            <button
              role="tab"
              aria-selected={activeTab === 'inferences'}
              onClick={() => setActiveTab('inferences')}
              style={{
                padding: 'var(--sp-2) var(--sp-4)',
                border: 'none',
                background: 'none',
                borderBottom: activeTab === 'inferences' ? '2px solid var(--primary)' : '2px solid transparent',
                fontWeight: activeTab === 'inferences' ? 700 : 500,
                color: activeTab === 'inferences' ? 'var(--primary)' : 'var(--text-muted)',
                cursor: 'pointer',
                fontSize: 'var(--fs-sm)',
                whiteSpace: 'nowrap',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
              }}
            >
              <Sparkles size={14} />
              <span>Market Inferences ({formData.inferences?.length || 0})</span>
            </button>
          </div>

          {/* TAB 1: Product & Value */}
          {activeTab === 'core' && (
            <div className="form-grid-2">
              <div className="card" style={{ padding: 'var(--sp-5)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
                <div className="form-group">
                  <label htmlFor="prof-name" className="label">Product / Business Name</label>
                  <input
                    id="prof-name"
                    type="text"
                    className="input"
                    value={formData.name || ''}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="prof-url" className="label">Website URL</label>
                  <input
                    id="prof-url"
                    type="url"
                    className="input"
                    placeholder="https://example.com"
                    value={formData.url || ''}
                    onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                  />
                </div>

                <div className="form-grid-2">
                  <div className="form-group">
                    <label htmlFor="prof-industry" className="label">Industry</label>
                    <input
                      id="prof-industry"
                      type="text"
                      className="input"
                      placeholder="e.g. SaaS, Developer Tools"
                      value={formData.industry || ''}
                      onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="prof-niche" className="label">Niche & Sub-category</label>
                    <input
                      id="prof-niche"
                      type="text"
                      className="input"
                      placeholder="e.g. CI/CD Observability"
                      value={formData.niche || ''}
                      onChange={(e) => setFormData({ ...formData, niche: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-grid-2">
                  <div className="form-group">
                    <label htmlFor="prof-geo" className="label">Geographic Market</label>
                    <input
                      id="prof-geo"
                      type="text"
                      className="input"
                      value={formData.geographic_market || 'Global'}
                      onChange={(e) => setFormData({ ...formData, geographic_market: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="prof-pricing" className="label">Pricing Model / Info</label>
                    <input
                      id="prof-pricing"
                      type="text"
                      className="input"
                      placeholder="e.g. Free tier + $29/mo seat"
                      value={formData.pricing_info || ''}
                      onChange={(e) => setFormData({ ...formData, pricing_info: e.target.value })}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label htmlFor="prof-main-product" className="label">Core Value Proposition</label>
                  <textarea
                    id="prof-main-product"
                    className="textarea"
                    rows={3}
                    placeholder="Concise statement of what your solution provides and why it matters."
                    value={formData.main_product_or_service || ''}
                    onChange={(e) => setFormData({ ...formData, main_product_or_service: e.target.value })}
                  />
                </div>
              </div>

              <div className="card" style={{ padding: 'var(--sp-5)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
                <div className="form-group">
                  <label htmlFor="prof-desc" className="label">Full Product Description</label>
                  <textarea
                    id="prof-desc"
                    className="textarea"
                    rows={3}
                    value={formData.description || ''}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="prof-features" className="label">Key Features (one per line)</label>
                  <textarea
                    id="prof-features"
                    className="textarea"
                    rows={3}
                    value={(formData.features || []).join('\n')}
                    onChange={(e) => handleListChange('features', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="prof-usps" className="label">Unique Selling Points / USPs (one per line)</label>
                  <textarea
                    id="prof-usps"
                    className="textarea"
                    rows={3}
                    placeholder="What sets this apart from competitors"
                    value={(formData.unique_selling_points || []).join('\n')}
                    onChange={(e) => handleListChange('unique_selling_points', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="prof-outcomes" className="label">Expected Customer Outcomes (one per line)</label>
                  <textarea
                    id="prof-outcomes"
                    className="textarea"
                    rows={3}
                    placeholder="Measurable results customers experience"
                    value={(formData.customer_outcomes || []).join('\n')}
                    onChange={(e) => handleListChange('customer_outcomes', e.target.value)}
                  />
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: ICP, Audience & Guardrails */}
          {activeTab === 'icp' && (
            <div className="form-grid-2">
              <div className="card" style={{ padding: 'var(--sp-5)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
                <div className="form-group">
                  <label htmlFor="prof-icp-text" className="label">Ideal Customer Profile (ICP Narrative)</label>
                  <textarea
                    id="prof-icp-text"
                    className="textarea"
                    rows={4}
                    placeholder="Describe the target team size, company maturity, technical stack, and pain context."
                    value={formData.icp || ''}
                    onChange={(e) => setFormData({ ...formData, icp: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="prof-target-roles" className="label">Target Roles / Job Titles (comma-separated)</label>
                  <input
                    id="prof-target-roles"
                    type="text"
                    className="input"
                    placeholder="Founder, VP Engineering, Product Lead, DevOps Engineer"
                    value={(formData.target_roles || []).join(', ')}
                    onChange={(e) => handleCommaListChange('target_roles', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="prof-target-industries" className="label">Target Industries (comma-separated)</label>
                  <input
                    id="prof-target-industries"
                    type="text"
                    className="input"
                    placeholder="B2B SaaS, E-commerce, Fintech, Healthcare Tech"
                    value={(formData.target_industries || []).join(', ')}
                    onChange={(e) => handleCommaListChange('target_industries', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="prof-demographics" className="label">Customer Demographics & Firmographics (one per line)</label>
                  <textarea
                    id="prof-demographics"
                    className="textarea"
                    rows={3}
                    placeholder="e.g. Seed to Series B, 5-50 engineers, remote-first"
                    value={(formData.customer_demographics || []).join('\n')}
                    onChange={(e) => handleListChange('customer_demographics', e.target.value)}
                  />
                </div>
              </div>

              {/* Guardrails / Negative ICP */}
              <div
                className="card"
                style={{
                  padding: 'var(--sp-5)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 'var(--sp-4)',
                  borderColor: 'var(--danger-border)',
                  background: 'var(--surface)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--sp-2)' }}>
                  <UserX size={18} color="var(--danger)" />
                  <h3 className="section-title" style={{ margin: 0, color: 'var(--danger-text)' }}>
                    Negative Target Audience (&ldquo;Not For&rdquo;)
                  </h3>
                </div>
                <p style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)', lineHeight: '1.45' }}>
                  Crucial safety guardrail: Kinds of people or companies who must <strong>never</strong> become leads. The qualification engine automatically penalizes or drops discussions matching these criteria.
                </p>

                <div className="form-group">
                  <label htmlFor="prof-not-for" className="label">
                    Disqualified Profiles (one per line)
                  </label>
                  <textarea
                    id="prof-not-for"
                    className="textarea"
                    rows={5}
                    placeholder="e.g.
B2C end-users looking for free consumer apps
Enterprise companies requiring on-premise air-gapped deployments
Users asking for hardware maintenance"
                    value={(formData.not_for || []).join('\n')}
                    onChange={(e) => handleListChange('not_for', e.target.value)}
                  />
                  <span className="helper-text">
                    Discussions from these personas will be scored low or filtered out.
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: Pain & Search Vocabulary */}
          {activeTab === 'pain' && (
            <div className="form-grid-2">
              <div className="card" style={{ padding: 'var(--sp-5)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
                <div className="form-group">
                  <label htmlFor="prof-pain-vocab" className="label">
                    Customer Pain Vocabulary (one phrase per line)
                  </label>
                  <textarea
                    id="prof-pain-vocab"
                    className="textarea"
                    rows={6}
                    placeholder="Phrases customers type when they have this problem, e.g.
too slow to debug
tired of fixing broken pipelines
why is AWS bill so high
alternative to Datadog
can anyone recommend a lightweight"
                    value={(formData.pain_vocabulary || []).join('\n')}
                    onChange={(e) => handleListChange('pain_vocabulary', e.target.value)}
                  />
                  <span className="helper-text">
                    The Search Planner directly uses these exact phrases to generate autonomous search queries on Reddit and Hacker News.
                  </span>
                </div>

                <div className="form-group">
                  <label htmlFor="prof-problems" className="label">Problems Solved (one per line)</label>
                  <textarea
                    id="prof-problems"
                    className="textarea"
                    rows={4}
                    placeholder="Key pain points your product alleviates"
                    value={(formData.problems_solved || []).join('\n')}
                    onChange={(e) => handleListChange('problems_solved', e.target.value)}
                  />
                </div>
              </div>

              <div className="card" style={{ padding: 'var(--sp-5)', display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
                <div className="form-group">
                  <label htmlFor="prof-frustrations" className="label">Customer Frustrations & Vent Terms (one per line)</label>
                  <textarea
                    id="prof-frustrations"
                    className="textarea"
                    rows={4}
                    placeholder="Emotional expressions and complaints"
                    value={(formData.customer_frustrations || []).join('\n')}
                    onChange={(e) => handleListChange('customer_frustrations', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="prof-triggers" className="label">Buying Trigger Events (one per line)</label>
                  <textarea
                    id="prof-triggers"
                    className="textarea"
                    rows={3}
                    placeholder="Events that force a buyer to look for a solution now (e.g. price hike, compliance audit, service outage)"
                    value={(formData.trigger_events || []).join('\n')}
                    onChange={(e) => handleListChange('trigger_events', e.target.value)}
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="prof-competitors" className="label">Competitors & Alternatives (comma-separated)</label>
                  <input
                    id="prof-competitors"
                    type="text"
                    className="input"
                    placeholder="e.g. Jira, Linear, Asana, Monday"
                    value={(formData.competitors_and_alternatives || []).join(', ')}
                    onChange={(e) => handleCommaListChange('competitors_and_alternatives', e.target.value)}
                  />
                  <span className="helper-text">
                    Threads mentioning these competitors will be flagged with competitor intelligence tags.
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* TAB 4: Facts */}
          {activeTab === 'facts' && (
            <div className="panel lead-table-panel">
              <div className="table-header">
                <div>
                  <h2>Extracted Verified Ground Truth Claims</h2>
                  <span>Claims extracted directly from your website pages and verified with source citations</span>
                </div>
              </div>
              {formData.facts?.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">
                    <Globe size={20} />
                  </div>
                  <strong>No verified claims extracted yet</strong>
                  <span>Analyze your website above to extract verifiable product claims.</span>
                </div>
              ) : (
                <div className="priority-list">
                  {formData.facts?.map((fact, idx) => (
                    <div
                      key={idx}
                      style={{
                        padding: 'var(--sp-4) var(--sp-5)',
                        borderBottom: '1px solid var(--border)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 'var(--sp-4)',
                      }}
                    >
                      <div>
                        <span className="badge badge-medium" style={{ marginRight: 'var(--sp-2)' }}>
                          {fact.category}
                        </span>
                        <span style={{ fontSize: 'var(--fs-base)', color: 'var(--text-main)' }}>
                          {fact.claim}
                        </span>
                      </div>
                      <a
                        href={fact.source_url}
                        target="_blank"
                        rel="noreferrer"
                        style={{
                          fontSize: 'var(--fs-xs)',
                          color: 'var(--primary)',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        <ExternalLink size={12} /> Source Page
                      </a>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* TAB 5: Inferences */}
          {activeTab === 'inferences' && (
            <div className="panel lead-table-panel">
              <div className="table-header">
                <div>
                  <h2>Market Inferences & Buying Signals</h2>
                  <span>Synthesized ICP nuances, purchase triggers, and audience intent patterns</span>
                </div>
              </div>
              {formData.inferences?.length === 0 ? (
                <div className="empty-state">
                  <div className="empty-icon">
                    <Sparkles size={20} />
                  </div>
                  <strong>No market inferences synthesized yet</strong>
                  <span>Provide more details or analyze additional pages to unlock market insights.</span>
                </div>
              ) : (
                <div className="priority-list">
                  {formData.inferences?.map((inf, idx) => (
                    <div
                      key={idx}
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
                          marginBottom: '4px',
                        }}
                      >
                        <span style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: 'var(--fs-base)' }}>
                          {inf.insight}
                        </span>
                        <span className="badge badge-high tabular">
                          {Math.round(inf.confidence * 100)}% Confidence
                        </span>
                      </div>
                      <div style={{ fontSize: 'var(--fs-xs)', color: 'var(--text-muted)' }}>
                        <strong>Evidence Basis:</strong> {inf.basis}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Bottom Save Action Bar */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--sp-3)', marginTop: 'var(--sp-6)' }}>
            <button className="btn btn-secondary" onClick={handleSaveProfile} disabled={loading}>
              <Save size={16} />
              <span>Save Profile Changes</span>
            </button>
            {!profile.confirmed && (
              <button className="btn btn-primary" onClick={handleConfirmProfile} disabled={loading}>
                <CheckCircle2 size={16} />
                <span>Confirm Profile for Discovery</span>
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default ProfileView;
