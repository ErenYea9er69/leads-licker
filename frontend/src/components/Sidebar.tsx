import React from 'react';
import {
  LayoutDashboard,
  Users,
  Building2,
  Compass,
  Inbox,
  MessageSquare,
  BarChart3,
  Settings,
  ShieldAlert,
  Flame,
} from 'lucide-react';

interface SidebarProps {
  currentTab: string;
  onSelectTab: (tab: string) => void;
  leadCounts: Record<string, number>;
  emergencyStop: boolean;
  teamPendingCheckpoints?: number;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onSelectTab,
  leadCounts,
  emergencyStop,
  teamPendingCheckpoints = 0,
}) => {
  const navItems = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    {
      id: 'team',
      label: 'CEO & Squad',
      icon: Users,
      badge: teamPendingCheckpoints > 0 ? teamPendingCheckpoints.toString() : undefined,
      badgeColor: '#fef3c7',
      badgeTextColor: '#b45309',
    },
    { id: 'profile', label: 'Business Profile', icon: Building2 },
    { id: 'discovery', label: 'Discovery Engine', icon: Compass },
    {
      id: 'leads',
      label: 'Leads Inbox',
      icon: Inbox,
      badge: leadCounts.total ? leadCounts.total.toString() : undefined,
      badgeColor: leadCounts.high_potential > 0 ? 'var(--success-bg)' : 'var(--surface-subtle)',
      badgeTextColor: leadCounts.high_potential > 0 ? 'var(--success-text)' : 'var(--text-muted)',
    },
    { id: 'reply_studio', label: 'Reply Studio', icon: MessageSquare },
    { id: 'analytics', label: 'Customer Insights', icon: BarChart3 },
    { id: 'settings', label: 'Settings & Safety', icon: Settings },
  ];

  return (
    <aside className="sidebar" aria-label="Main Navigation">
      {/* Brand Header */}
      <div className="sidebar-brand">
        <div className="brand-icon">
          <Flame size={18} />
        </div>
        <div className="brand-text">
          <div className="brand-title">Leads Licker</div>
          <div className="brand-subtitle">Customer Discovery</div>
        </div>
      </div>

      {/* Emergency Stop Banner if active */}
      {emergencyStop && (
        <div className="sidebar-emergency-alert" role="status">
          <ShieldAlert size={15} />
          <span>STOP ACTIVE</span>
        </div>
      )}

      {/* Nav List */}
      <nav className="sidebar-nav">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`nav-item ${isActive ? 'active' : ''}`}
              aria-current={isActive ? 'page' : undefined}
            >
              <div className="nav-item-content">
                <Icon size={16} />
                <span>{item.label}</span>
              </div>
              {item.badge && (
                <span
                  className="nav-badge"
                  style={{
                    background: item.badgeColor,
                    color: item.badgeTextColor,
                  }}
                >
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="sidebar-footer">
        <span>Engine v3.3.1</span>
        <span className="status-indicator">
          <span className="status-dot status-dot-green" />
          <span>Ready</span>
        </span>
      </div>
    </aside>
  );
};
