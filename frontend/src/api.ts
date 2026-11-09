import type {
  AnalyticsSummary,
  AskCeoResponse,
  BusinessProfile,
  Campaign,
  CEOIntakeState,
  CheckpointResolution,
  ConnectionsGuide,
  DirectiveDetail,
  DirectiveSummary,
  GeneratedReply,
  LeadQualification,
  LinkedAccountDetail,
  LintReport,
  MemoryItem,
  NextStep,
  PlatformInfo,
  PostingSettings,
  SettingsPayload,
  TeamReport,
  TeamRoster,
} from './types';

const BASE_URL = '/api';

function formatApiError(status: number, data: any, rawText: string): string {
  if (data && data.detail) {
    if (typeof data.detail === 'string') {
      const msg = data.detail.trim();
      if (msg.includes('Confirm the business profile before launching')) {
        return 'Please review and confirm your Business Profile before launching a campaign.';
      }
      if (msg.includes('A campaign is already running')) {
        return 'Another campaign is currently running. You can cancel it or wait for it to complete.';
      }
      if (msg.includes('Campaign is not running')) {
        return 'This campaign has already completed or is not currently running.';
      }
      if (msg.includes('Rate limit exceeded')) {
        return 'Too many requests in a short period. Please wait a moment and try again.';
      }
      if (msg.includes('Business profile required')) {
        return 'A business profile is required before generating replies.';
      }
      if (msg.includes('A custom reply needs text')) {
        return 'Please write your custom reply text before approving.';
      }
      if (msg.includes('Invalid or missing API key')) {
        return 'API authentication failed. Please check your API key.';
      }
      if (msg.includes('Set AGENT_REACH_API_KEY')) {
        return 'Remote access is restricted. Set AGENT_REACH_API_KEY on the server for external connections.';
      }
      return msg;
    }
    if (Array.isArray(data.detail)) {
      const items = data.detail
        .map((item: any) => {
          const field = Array.isArray(item.loc) ? item.loc[item.loc.length - 1] : 'field';
          return `${field}: ${item.msg || 'invalid value'}`;
        })
        .join(', ');
      return `Input validation error (${items})`;
    }
  }

  if (status === 400) return 'Invalid request. Please check the provided information.';
  if (status === 401) return 'Authentication required. Please check your credentials.';
  if (status === 403) return 'Access denied. You do not have permission for this request.';
  if (status === 404) return 'The requested resource was not found.';
  if (status === 409) return 'Request conflict. An operation is already in progress or cannot be completed.';
  if (status === 429) return 'Rate limit exceeded. Please wait a moment before trying again.';
  if (status === 502) return 'AI provider or external service error. Please verify your AI settings and keys.';
  if (status >= 500) return 'An unexpected server error occurred. Please check the backend logs.';

  return rawText ? rawText.slice(0, 160) : `Request failed (HTTP ${status}).`;
}

async function handleResponse<T>(res: Response): Promise<T> {
  const text = await res.text();
  let json: any = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    // not JSON
  }

  if (!res.ok) {
    const errorMsg = formatApiError(res.status, json, text);
    throw new Error(errorMsg);
  }

  return (json ?? {}) as T;
}

export const api = {
  // Profile
  async getProfile(): Promise<BusinessProfile | null> {
    const res = await fetch(`${BASE_URL}/profile`);
    const data = await handleResponse<{ profile: BusinessProfile | null }>(res);
    return data.profile;
  },

  async extractFromUrl(url: string): Promise<BusinessProfile> {
    const res = await fetch(`${BASE_URL}/profile/extract-url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    const data = await handleResponse<{ ok: boolean; profile: BusinessProfile }>(res);
    return data.profile;
  },

  async extractFromManual(name: string, description: string): Promise<BusinessProfile> {
    const res = await fetch(`${BASE_URL}/profile/extract-manual`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name || undefined, description }),
    });
    const data = await handleResponse<{ ok: boolean; profile: BusinessProfile }>(res);
    return data.profile;
  },

  async updateProfile(profile: BusinessProfile): Promise<BusinessProfile> {
    const res = await fetch(`${BASE_URL}/profile/update`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile),
    });
    const data = await handleResponse<{ ok: boolean; profile: BusinessProfile }>(res);
    return data.profile;
  },

  async confirmProfile(): Promise<BusinessProfile> {
    const res = await fetch(`${BASE_URL}/profile/confirm`, {
      method: 'POST',
    });
    const data = await handleResponse<{ ok: boolean; profile: BusinessProfile }>(res);
    return data.profile;
  },

  // Campaigns
  async listCampaigns(): Promise<Campaign[]> {
    const res = await fetch(`${BASE_URL}/campaigns`);
    const data = await handleResponse<{ campaigns: Campaign[] }>(res);
    return data.campaigns || [];
  },

  async launchCampaign(name: string, platforms: string[], maxLeads: number): Promise<string> {
    const res = await fetch(`${BASE_URL}/campaigns/launch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, platforms, max_leads: maxLeads }),
    });
    const data = await handleResponse<{ ok: boolean; campaign_id: string }>(res);
    return data.campaign_id;
  },

  async getCampaign(id: string): Promise<Campaign> {
    const res = await fetch(`${BASE_URL}/campaigns/${id}`);
    const data = await handleResponse<{ campaign: Campaign }>(res);
    return data.campaign;
  },

  async cancelCampaign(id: string): Promise<{ ok: boolean; message: string }> {
    const res = await fetch(`${BASE_URL}/campaigns/${id}/cancel`, {
      method: 'POST',
    });
    return await handleResponse<{ ok: boolean; message: string }>(res);
  },

  // Platforms
  async getPlatforms(): Promise<PlatformInfo> {
    const res = await fetch(`${BASE_URL}/platforms`);
    return await handleResponse<PlatformInfo>(res);
  },

  // Leads
  async listLeads(filters: {
    min_score?: number;
    platform?: string;
    classification?: string;
    pain_point_category?: string;
    buying_intent?: string;
    query?: string;
    limit?: number;
    offset?: number;
  } = {}): Promise<LeadQualification[]> {
    const params = new URLSearchParams();
    if (filters.min_score !== undefined) params.append('min_score', filters.min_score.toString());
    if (filters.platform) params.append('platform', filters.platform);
    if (filters.classification) params.append('classification', filters.classification);
    if (filters.pain_point_category) params.append('pain_point_category', filters.pain_point_category);
    if (filters.buying_intent) params.append('buying_intent', filters.buying_intent);
    if (filters.query) params.append('query', filters.query);
    if (filters.limit !== undefined) params.append('limit', filters.limit.toString());
    if (filters.offset !== undefined) params.append('offset', filters.offset.toString());

    const res = await fetch(`${BASE_URL}/leads?${params.toString()}`);
    const data = await handleResponse<{ leads: LeadQualification[] }>(res);
    return data.leads || [];
  },

  async getLeadCounts(): Promise<Record<string, number>> {
    const res = await fetch(`${BASE_URL}/leads/counts`);
    return await handleResponse<Record<string, number>>(res);
  },

  async getLead(id: string): Promise<{ lead: LeadQualification; reply?: GeneratedReply | null; replies?: GeneratedReply[] }> {
    const res = await fetch(`${BASE_URL}/leads/${id}`);
    return await handleResponse<{ lead: LeadQualification; reply?: GeneratedReply | null; replies?: GeneratedReply[] }>(res);
  },

  async getRepliesForLead(leadId: string): Promise<GeneratedReply[]> {
    const res = await fetch(`${BASE_URL}/leads/${leadId}/replies`);
    const data = await handleResponse<{ replies: GeneratedReply[] }>(res);
    return data.replies || [];
  },

  // Replies
  async getReply(leadId: string): Promise<GeneratedReply> {
    const res = await fetch(`${BASE_URL}/replies/${leadId}`);
    const data = await handleResponse<{ reply: GeneratedReply }>(res);
    return data.reply;
  },

  async generateReply(
    leadId: string,
    options?: { account?: string; target_mode?: string; comment_id?: string; keep_others?: boolean }
  ): Promise<GeneratedReply> {
    const res = await fetch(`${BASE_URL}/replies/${leadId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options || {}),
    });
    const data = await handleResponse<{ ok: boolean; reply: GeneratedReply }>(res);
    return data.reply;
  },

  async approveReply(
    leadId: string,
    editedReply?: string,
    selectedVersion?: string,
    replyId?: string
  ): Promise<GeneratedReply> {
    const res = await fetch(`${BASE_URL}/replies/${leadId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ edited_reply: editedReply, selected_version: selectedVersion, reply_id: replyId }),
    });
    const data = await handleResponse<{ ok: boolean; reply: GeneratedReply }>(res);
    return data.reply;
  },

  async publishReply(
    leadId: string,
    replyId?: string
  ): Promise<{
    success: boolean;
    action?: string;
    text?: string;
    target_url?: string;
    reason?: string;
    message?: string;
  }> {
    const res = await fetch(`${BASE_URL}/replies/${leadId}/publish`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reply_id: replyId }),
    });
    return await handleResponse<{
      success: boolean;
      action?: string;
      text?: string;
      target_url?: string;
      reason?: string;
      message?: string;
    }>(res);
  },

  async confirmPublished(leadId: string): Promise<{ success: boolean; message?: string; reason?: string }> {
    const res = await fetch(`${BASE_URL}/replies/${leadId}/confirm-published`, { method: 'POST' });
    return await handleResponse<{ success: boolean; message?: string; reason?: string }>(res);
  },

  // Linked Accounts
  async getAccounts(): Promise<LinkedAccountDetail[]> {
    const res = await fetch(`${BASE_URL}/accounts`);
    const data = await handleResponse<{ accounts: LinkedAccountDetail[] }>(res);
    return data.accounts || [];
  },

  async linkAccount(data: {
    platform: string;
    handle: string;
    alias?: string;
    focus?: string[];
    mode?: 'manual' | 'api';
  }): Promise<LinkedAccountDetail> {
    const res = await fetch(`${BASE_URL}/accounts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const resData = await handleResponse<{ ok: boolean; account: LinkedAccountDetail }>(res);
    return resData.account;
  },

  async unlinkAccount(platform: string, handle: string): Promise<boolean> {
    const res = await fetch(`${BASE_URL}/accounts/${encodeURIComponent(platform)}/${encodeURIComponent(handle)}`, {
      method: 'DELETE',
    });
    const data = await handleResponse<{ ok: boolean }>(res);
    return data.ok;
  },

  async setAccountVoice(platform: string, handle: string, samples: string[]): Promise<boolean> {
    const res = await fetch(`${BASE_URL}/accounts/${encodeURIComponent(platform)}/${encodeURIComponent(handle)}/voice`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ samples }),
    });
    const data = await handleResponse<{ ok: boolean }>(res);
    return data.ok;
  },

  // Connections Guide
  async getConnections(source?: string): Promise<ConnectionsGuide> {
    const url = source ? `${BASE_URL}/connections?source=${encodeURIComponent(source)}` : `${BASE_URL}/connections`;
    const res = await fetch(url);
    return await handleResponse<ConnectionsGuide>(res);
  },

  // Voice & Copywriting Linter
  async lintText(text: string, kind?: string, platform?: string, leadId?: string): Promise<LintReport> {
    const res = await fetch(`${BASE_URL}/voice/lint`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, kind, platform, lead_id: leadId }),
    });
    return await handleResponse<LintReport>(res);
  },

  async getDisclosures(): Promise<{ phrases: string[] }> {
    const res = await fetch(`${BASE_URL}/voice/disclosures`);
    return await handleResponse<{ phrases: string[] }>(res);
  },

  // Analytics
  async getAnalytics(): Promise<AnalyticsSummary> {
    const res = await fetch(`${BASE_URL}/analytics`);
    return await handleResponse<AnalyticsSummary>(res);
  },

  // Settings
  async getSettings(): Promise<SettingsPayload> {
    const res = await fetch(`${BASE_URL}/settings`);
    return await handleResponse<SettingsPayload>(res);
  },

  async updateSettings(settings: {
    posting_settings?: Partial<PostingSettings>;
    llm_settings?: Record<string, any>;
    mcp_settings?: Partial<import('./types').MCPSettings>;
  }): Promise<void> {
    const res = await fetch(`${BASE_URL}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    await handleResponse<{ ok: boolean }>(res);
  },

  getExportUrl(format: 'json' | 'csv', minScore: number = 0): string {
    return `${BASE_URL}/export?format=${format}&min_score=${minScore}`;
  },

  // ── Team & CEO Layer ──
  team: {
    async ask(message: string): Promise<AskCeoResponse> {
      const res = await fetch(`${BASE_URL}/team/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      });
      return await handleResponse<AskCeoResponse>(res);
    },

    async listDirectives(): Promise<{ directives: DirectiveSummary[]; model_configured: boolean }> {
      const res = await fetch(`${BASE_URL}/team/directives`);
      return await handleResponse<{ directives: DirectiveSummary[]; model_configured: boolean }>(res);
    },

    async getDirective(id: string): Promise<DirectiveDetail> {
      const res = await fetch(`${BASE_URL}/team/directives/${id}`);
      return await handleResponse<DirectiveDetail>(res);
    },

    async runDirective(id: string): Promise<{ started: boolean; directive_id: string }> {
      const res = await fetch(`${BASE_URL}/team/directives/${id}/run`, {
        method: 'POST',
      });
      return await handleResponse<{ started: boolean; directive_id: string }>(res);
    },

    async getReport(id: string): Promise<TeamReport> {
      const res = await fetch(`${BASE_URL}/team/directives/${id}/report`);
      return await handleResponse<TeamReport>(res);
    },

    async resolveCheckpoint(
      taskId: string,
      decision: 'approve' | 'reject',
      message: string
    ): Promise<CheckpointResolution> {
      const res = await fetch(`${BASE_URL}/team/tasks/${taskId}/checkpoint`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, message }),
      });
      return await handleResponse<CheckpointResolution>(res);
    },

    async getNextStep(id: string): Promise<NextStep> {
      const res = await fetch(`${BASE_URL}/team/directives/${id}/next`);
      return await handleResponse<NextStep>(res);
    },

    async cancelDirective(
      id: string,
      reason: string = ''
    ): Promise<{ directive_id: string; status: string; tasks_stopped: number }> {
      const res = await fetch(`${BASE_URL}/team/directives/${id}/cancel`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason }),
      });
      return await handleResponse<{ directive_id: string; status: string; tasks_stopped: number }>(res);
    },

    async getMemory(): Promise<MemoryItem[]> {
      const res = await fetch(`${BASE_URL}/team/memory`);
      return await handleResponse<MemoryItem[]>(res);
    },

    async addMemory(text: string): Promise<{ remembered: string; id: number }> {
      const res = await fetch(`${BASE_URL}/team/memory`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      return await handleResponse<{ remembered: string; id: number }>(res);
    },

    async deleteMemory(id: number): Promise<{ forgotten: number }> {
      const res = await fetch(`${BASE_URL}/team/memory/${id}`, {
        method: 'DELETE',
      });
      return await handleResponse<{ forgotten: number }>(res);
    },

    async getIntake(): Promise<CEOIntakeState> {
      const res = await fetch(`${BASE_URL}/team/intake`);
      return await handleResponse<CEOIntakeState>(res);
    },

    async submitIntake(
      answers?: Record<string, any>,
      skip?: string[]
    ): Promise<CEOIntakeState> {
      const res = await fetch(`${BASE_URL}/team/intake`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers, skip }),
      });
      return await handleResponse<CEOIntakeState>(res);
    },

    async resetIntake(): Promise<CEOIntakeState> {
      const res = await fetch(`${BASE_URL}/team/intake`, {
        method: 'DELETE',
      });
      return await handleResponse<CEOIntakeState>(res);
    },

    async getRoster(): Promise<TeamRoster> {
      const res = await fetch(`${BASE_URL}/team/roster`);
      return await handleResponse<TeamRoster>(res);
    },
  },

  // System Diagnostics & Multi-Mode
  async getSystemStatus(): Promise<any> {
    const res = await fetch(`${BASE_URL}/system/status`);
    return await handleResponse<any>(res);
  },

  async getHealth(): Promise<any> {
    const res = await fetch(`${BASE_URL}/health`);
    return await handleResponse<any>(res);
  },
};
