import React, { useState } from 'react';

export interface StudioRightPanelProps {
  onSelectProject?: (projectId: string) => void;
}

export const StudioRightPanel: React.FC<StudioRightPanelProps> = ({ onSelectProject }) => {
  const [activeTab, setActiveTab] = useState<'recent' | 'templates' | 'activity'>('recent');

  const projects = [
    {
      id: 'proj_1',
      title: 'Rừng Xanh Kỳ Diệu',
      status: 'Active',
      statusColor: '#10b981',
      episodes: '12 episodes',
      date: '12/08/2025',
      gradient: 'linear-gradient(135deg, #059669 0%, #10b981 100%)',
      iconEmoji: '🌲',
    },
    {
      id: 'proj_2',
      title: 'Những Người Bạn Từ Vũ Trụ',
      status: 'Planning',
      statusColor: '#3b82f6',
      episodes: '1 episode',
      date: '10/08/2025',
      gradient: 'linear-gradient(135deg, #1d4ed8 0%, #3b82f6 100%)',
      iconEmoji: '🚀',
    },
    {
      id: 'proj_3',
      title: 'Thành Phố Mơ Ước',
      status: 'Draft',
      statusColor: '#6b7280',
      episodes: '0 episode',
      date: '08/08/2025',
      gradient: 'linear-gradient(135deg, #d97706 0%, #f59e0b 100%)',
      iconEmoji: '🌆',
    },
    {
      id: 'proj_4',
      title: 'Cá Voi Và Đại Dương',
      status: 'Draft',
      statusColor: '#6b7280',
      episodes: '0 episode',
      date: '05/08/2025',
      gradient: 'linear-gradient(135deg, #0284c7 0%, #38bdf8 100%)',
      iconEmoji: '🐋',
    },
    {
      id: 'proj_5',
      title: 'Bí Mật Ngôi Làng Xanh',
      status: 'Draft',
      statusColor: '#6b7280',
      episodes: '0 episode',
      date: '01/08/2025',
      gradient: 'linear-gradient(135deg, #16a34a 0%, #4ade80 100%)',
      iconEmoji: '🏡',
    },
  ];

  return (
    <aside className="studio-right-panel">
      {/* Top Banner Card */}
      <div className="right-panel-hero-card">
        <div className="hero-card-content">
          <div className="hero-card-title">WindAgent Studio v1.0</div>
          <div className="hero-card-sub">Story-first. Agent-powered.</div>
          <div className="hero-card-play-btn">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
          </div>
        </div>
        <div className="hero-card-art-preview">
          <div className="art-gradient-bg"></div>
        </div>
      </div>

      {/* Tabs */}
      <div className="right-panel-tabs">
        <button
          className={`panel-tab ${activeTab === 'recent' ? 'active' : ''}`}
          onClick={() => setActiveTab('recent')}
        >
          Recent Projects
        </button>
        <button
          className={`panel-tab ${activeTab === 'templates' ? 'active' : ''}`}
          onClick={() => setActiveTab('templates')}
        >
          Templates
        </button>
        <button
          className={`panel-tab ${activeTab === 'activity' ? 'active' : ''}`}
          onClick={() => setActiveTab('activity')}
        >
          Activity
        </button>
      </div>

      {/* Content based on tab */}
      {activeTab === 'recent' && (
        <div className="recent-projects-list">
          {projects.map((proj) => (
            <div
              key={proj.id}
              className="project-item-card"
              onClick={() => onSelectProject?.(proj.id)}
            >
              <div className="project-thumb" style={{ background: proj.gradient }}>
                <span className="thumb-emoji">{proj.iconEmoji}</span>
              </div>
              <div className="project-meta">
                <div className="project-title">{proj.title}</div>
                <div className="project-status-row">
                  <span className="status-dot" style={{ backgroundColor: proj.statusColor }}></span>
                  <span className="status-name">{proj.status}</span>
                </div>
                <div className="project-episodes">{proj.episodes}</div>
              </div>
              <div className="project-right">
                <button className="project-more-btn" aria-label="More options">•••</button>
                <div className="project-date">{proj.date}</div>
              </div>
            </div>
          ))}
          <a href="#/studio/projects" className="view-all-projects-link">
            View all projects <span>→</span>
          </a>
        </div>
      )}

      {activeTab === 'templates' && (
        <div className="right-panel-empty-tab">
          <p>Preset templates available for short screenplays, drama series, and documentary arcs.</p>
        </div>
      )}

      {activeTab === 'activity' && (
        <div className="right-panel-empty-tab">
          <p>Recent agent runs, screenplay locks, and revision events will appear here.</p>
        </div>
      )}

      {/* Useful Links Section */}
      <div className="useful-links-section">
        <div className="useful-links-title">Useful Links</div>
        <div className="useful-links-grid">
          <div className="link-item">
            <div className="link-icon">📄</div>
            <div className="link-text">
              <span className="link-label">Documentation</span>
              <span className="link-desc">Read the docs →</span>
            </div>
          </div>
          <div className="link-item">
            <div className="link-icon">📦</div>
            <div className="link-text">
              <span className="link-label">Changelog</span>
              <span className="link-desc">View latest updates →</span>
            </div>
          </div>
          <div className="link-item">
            <div className="link-icon">🗺️</div>
            <div className="link-text">
              <span className="link-label">Roadmap</span>
              <span className="link-desc">See what's next →</span>
            </div>
          </div>
          <div className="link-item">
            <div className="link-icon">👥</div>
            <div className="link-text">
              <span className="link-label">Community</span>
              <span className="link-desc">Join the discussion →</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};

export default StudioRightPanel;
