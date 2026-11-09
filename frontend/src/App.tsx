import React, { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, LoaderCircle, X } from 'lucide-react';
import { Sidebar } from './components/Sidebar';
import { OverviewView } from './components/OverviewView';
import { TeamView } from './components/TeamView';
import { ProfileView } from './components/ProfileView';
import { DiscoveryView } from './components/DiscoveryView';
import { LeadsView } from './components/LeadsView';
import { ReplyStudioView } from './components/ReplyStudioView';
import { AnalyticsView } from './components/AnalyticsView';
import { SettingsView } from './components/SettingsView';
import type { BusinessProfile, LeadQualification } from './types';
import { api } from './api';

const routeToTab: Record<string, string> = {
  '/': 'overview',
  '/overview': 'overview',
  '/team': 'team',
  '/profile': 'profile',
  '/discovery': 'discovery',
  '/leads': 'leads',
  '/reply-studio': 'reply_studio',
  '/analytics': 'analytics',
  '/settings': 'settings',
};

const tabToRoute: Record<string, string> = Object.fromEntries(
  Object.entries(routeToTab).map(([route, tab]) => [tab, route])
);

const currentLocation = () => {
  const path = window.location.pathname.replace(/\/$/, '') || '/';
  return {
    tab: routeToTab[path] || 'overview',
    leadId: new URLSearchParams(window.location.search).get('lead') || undefined,
  };
};

export const App: React.FC = () => {
  const initial = currentLocation();
  const [currentTab, setCurrentTab] = useState(initial.tab);
  const [profile, setProfile] = useState<BusinessProfile | null>(null);
  const [leads, setLeads] = useState<LeadQualification[]>([]);
  const [leadCounts, setLeadCounts] = useState<Record<string, number>>({});
  const [emergencyStop, setEmergencyStop] = useState(false);
  const [replyStudioLeadId, setReplyStudioLeadId] = useState<string | undefined>(initial.leadId);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState<{ type: 'error' | 'success'; message: string } | null>(null);
  const [teamPendingCheckpoints, setTeamPendingCheckpoints] = useState(0);

  const refreshData = async () => {
    setLoading(true);
    try {
      const [prof, leadList, counts, settingsData, teamDirs] = await Promise.all([
        api.getProfile(),
        api.listLeads({ limit: 25, offset: 0 }),
        api.getLeadCounts(),
        api.getSettings(),
        api.team.listDirectives().catch(() => ({ directives: [], model_configured: false })),
      ]);
      setProfile(prof);
      setLeads(leadList);
      setLeadCounts(counts);
      setEmergencyStop(settingsData.posting_settings?.emergency_stop || false);
      const waiting = (teamDirs.directives || []).filter((d) => d.status === 'waiting_owner');
      setTeamPendingCheckpoints(waiting.length);
    } catch (error) {
      setNotice({
        type: 'error',
        message: error instanceof Error ? error.message : 'Could not load workspace data.',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refreshData();
  }, []);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 4500);
    return () => window.clearTimeout(timer);
  }, [notice]);

  useEffect(() => {
    const onPopState = () => {
      const next = currentLocation();
      setCurrentTab(next.tab);
      setReplyStudioLeadId(next.leadId);
    };
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const handleNavigate = (tab: string, leadId?: string) => {
    const route = tabToRoute[tab] || '/';
    const url = new URL(window.location.href);
    url.pathname = route;
    if (leadId) url.searchParams.set('lead', leadId);
    else url.searchParams.delete('lead');
    window.history.pushState({}, '', url);
    setCurrentTab(tab);
    setReplyStudioLeadId(leadId);
  };

  const pageTitles: Record<string, string> = {
    overview: 'Overview',
    team: 'CEO & Autonomous Squad',
    profile: 'Business Profile',
    discovery: 'Discovery Engine',
    leads: 'Leads Inbox',
    reply_studio: 'Reply Studio',
    analytics: 'Customer Insights',
    settings: 'Settings & Safety',
  };

  return (
    <div className="app-container">
      <a href="#main-content" className="skip-link">Skip to main content</a>
      <Sidebar
        currentTab={currentTab}
        onSelectTab={handleNavigate}
        leadCounts={leadCounts}
        emergencyStop={emergencyStop}
        teamPendingCheckpoints={teamPendingCheckpoints}
      />
      <main id="main-content" className="main-content">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Leads Licker</span>
            <span className="breadcrumb-separator">/</span>
            <strong>{pageTitles[currentTab]}</strong>
            {profile && <span className="workspace-chip">{profile.name}</span>}
          </div>
          <div className="topbar-status">
            <span className={`status-dot ${emergencyStop ? 'status-dot-red' : 'status-dot-green'}`} />
            <span>{emergencyStop ? 'Emergency stop active' : 'Workspace ready'}</span>
          </div>
        </header>

        {notice && (
          <aside
            className={`toast toast-${notice.type}`}
            role={notice.type === 'error' ? 'alert' : 'status'}
            aria-live="polite"
          >
            <span className="toast-icon">
              {notice.type === 'error' ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
            </span>
            <span className="toast-message">{notice.message}</span>
            <button
              className="toast-dismiss"
              onClick={() => setNotice(null)}
              aria-label="Dismiss notification"
            >
              <X size={15} />
            </button>
          </aside>
        )}

        {loading ? (
          <div className="loading-state">
            <LoaderCircle className="spin" size={24} />
            <span>Loading workspace intelligence…</span>
          </div>
        ) : (
          <div className="view-scroll">
            {currentTab === 'overview' && (
              <OverviewView
                profile={profile}
                leads={leads}
                leadCounts={leadCounts}
                onNavigate={handleNavigate}
                onLaunchCampaign={() => handleNavigate('discovery')}
              />
            )}
            {currentTab === 'team' && (
              <TeamView
                profile={profile}
                onNavigateToLeads={() => handleNavigate('leads')}
                onNavigateToReplyStudio={(leadId) => handleNavigate('reply_studio', leadId)}
                onNavigateToProfile={() => handleNavigate('profile')}
              />
            )}
            {currentTab === 'profile' && (
              <ProfileView
                profile={profile}
                onProfileUpdated={(updated) => {
                  setProfile(updated);
                  void refreshData();
                }}
              />
            )}
            {currentTab === 'discovery' && (
              <DiscoveryView
                profile={profile}
                onCampaignFinished={refreshData}
                onNavigateToProfile={() => handleNavigate('profile')}
              />
            )}
            {currentTab === 'leads' && (
              <LeadsView
                leads={leads}
                onOpenReplyStudio={(id) => handleNavigate('reply_studio', id)}
              />
            )}
            {currentTab === 'reply_studio' && (
              <ReplyStudioView
                initialLeadId={replyStudioLeadId}
                leads={leads}
                onNavigateToDiscovery={() => handleNavigate('discovery')}
              />
            )}
            {currentTab === 'analytics' && <AnalyticsView />}
            {currentTab === 'settings' && <SettingsView />}
          </div>
        )}
      </main>
    </div>
  );
};

export default App;
