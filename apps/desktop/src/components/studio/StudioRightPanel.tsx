import React, { useState } from 'react';
import {
  Film,
  Sparkles,
  Bot,
  Users,
  Settings,
  ArrowRight,
  PlusCircle,
  BookOpen,
  Activity,
} from 'lucide-react';

export interface StudioSeriesItem {
  id: string;
  title: string;
  episode_count: number;
  created_at?: string;
}

export interface StudioRightPanelProps {
  seriesList?: StudioSeriesItem[];
  capabilities?: Record<string, string>;
  onSelectProject?: (projectId: string) => void;
  onApplyTemplate?: (templateTitle: string, templateDesc?: string) => void;
  onNavigateTab?: (hash: string) => void;
}

const TEMPLATE_PRESETS = [
  {
    id: 'tmpl_scifi',
    title: 'Cyberpunk Odyssey 2099',
    desc: 'Series khoa học viễn tưởng thế giới ngầm neon, cyborg và AI nổi dậy.',
    tag: 'Sci-Fi / Cyberpunk',
    color: '#4d8eff',
  },
  {
    id: 'tmpl_fantasy',
    title: 'Biên Niên Sử Vùng Đất Rồng',
    desc: 'Hành trình phiêu lưu sử thi kỳ ảo qua 7 vương quốc phép thuật cổ đại.',
    tag: 'Fantasy / Adventure',
    color: '#4edea3',
  },
  {
    id: 'tmpl_mystery',
    title: 'Án Mạng Lúc Nửa Đêm',
    desc: 'Trinh thám kịch tính với cú lật mặt bất ngờ tại dinh thự cổ.',
    tag: 'Mystery / Detective',
    color: '#f59e0b',
  },
  {
    id: 'tmpl_comedy',
    title: 'Biệt Đội Siêu Lầy Trái Đất',
    desc: 'Hài hước sitcom về nhóm sinh vật ngoài hành tinh ẩn thân trong chung cư.',
    tag: 'Sitcom / Comedy',
    color: '#c0c1ff',
  },
];

export const StudioRightPanel: React.FC<StudioRightPanelProps> = ({
  seriesList = [],
  capabilities = {},
  onSelectProject,
  onApplyTemplate,
  onNavigateTab,
}) => {
  const [activeTab, setActiveTab] = useState<'recent' | 'templates' | 'system'>('recent');

  const handleLinkClick = (hash: string) => {
    if (onNavigateTab) {
      onNavigateTab(hash);
    } else {
      window.location.hash = hash;
    }
  };

  return (
    <aside className="studio-right-panel">
      {/* Top Hero Card */}
      <div className="right-panel-hero-card">
        <div className="hero-card-content">
          <div className="hero-card-title">WindAgent Studio</div>
          <div className="hero-card-sub">AI Screenplay & Story Swarm</div>
          <div
            className="hero-card-play-btn"
            title="Khởi tạo kịch bản mới"
            onClick={() => {
              const inputEl = document.getElementById('new-series-input');
              if (inputEl) {
                inputEl.focus();
                inputEl.scrollIntoView({ behavior: 'smooth' });
              }
            }}
          >
            <Sparkles size={14} />
          </div>
        </div>
        <div className="hero-card-art-preview">
          <div className="art-gradient-bg"></div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="right-panel-tabs">
        <button
          className={`panel-tab ${activeTab === 'recent' ? 'active' : ''}`}
          onClick={() => setActiveTab('recent')}
        >
          Dự Án ({seriesList.length})
        </button>
        <button
          className={`panel-tab ${activeTab === 'templates' ? 'active' : ''}`}
          onClick={() => setActiveTab('templates')}
        >
          Templates
        </button>
        <button
          className={`panel-tab ${activeTab === 'system' ? 'active' : ''}`}
          onClick={() => setActiveTab('system')}
        >
          Hệ Thống
        </button>
      </div>

      {/* Tab 1: Real Recent Projects from Database */}
      {activeTab === 'recent' && (
        <div className="recent-projects-list">
          {seriesList.length === 0 ? (
            <div className="right-panel-empty-tab">
              <Film size={28} color="#8c909f" style={{ margin: '0 auto 8px auto' }} />
              <p>Chưa có dự án nào trong Database.</p>
              <button
                className="btn-quick-new"
                style={{ margin: '8px auto', fontSize: '0.76rem', padding: '6px 12px' }}
                onClick={() => {
                  const inputEl = document.getElementById('new-series-input');
                  if (inputEl) {
                    inputEl.focus();
                    inputEl.scrollIntoView({ behavior: 'smooth' });
                  }
                }}
              >
                <PlusCircle size={14} />
                <span>Tạo Series Đầu Tiên</span>
              </button>
            </div>
          ) : (
            <>
              {seriesList.map((proj, idx) => (
                <div
                  key={proj.id}
                  className="project-item-card"
                  onClick={() => onSelectProject?.(proj.id)}
                  style={{ cursor: 'pointer' }}
                >
                  <div
                    className="project-thumb"
                    style={{
                      background: `linear-gradient(135deg, ${
                        idx % 3 === 0 ? '#1e3a8a, #3b82f6' : idx % 3 === 1 ? '#064e3b, #10b981' : '#581c87, #a855f7'
                      })`,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Film size={16} color="#ffffff" />
                  </div>
                  <div className="project-meta">
                    <div className="project-title" title={proj.title}>
                      {proj.title}
                    </div>
                    <div className="project-status-row">
                      <span className="status-dot" style={{ backgroundColor: '#4edea3' }}></span>
                      <span className="status-name">{proj.episode_count} tập phim</span>
                    </div>
                    <div className="project-episodes" style={{ fontFamily: 'var(--font-mono)' }}>
                      {proj.id.slice(0, 14)}…
                    </div>
                  </div>
                  <div className="project-right">
                    <ArrowRight size={14} color="#8c909f" />
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      )}

      {/* Tab 2: Story Starter Templates */}
      {activeTab === 'templates' && (
        <div className="recent-projects-list">
          {TEMPLATE_PRESETS.map((tmpl) => (
            <div
              key={tmpl.id}
              className="project-item-card"
              onClick={() => onApplyTemplate?.(tmpl.title, tmpl.desc)}
              style={{ cursor: 'pointer' }}
              title="Nhấn để áp dụng template này"
            >
              <div
                className="project-thumb"
                style={{
                  background: `linear-gradient(135deg, ${tmpl.color}33, ${tmpl.color}88)`,
                  border: `1px solid ${tmpl.color}aa`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <BookOpen size={16} color={tmpl.color} />
              </div>
              <div className="project-meta">
                <div className="project-title">{tmpl.title}</div>
                <div className="project-status-row">
                  <span
                    style={{
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      color: tmpl.color,
                    }}
                  >
                    {tmpl.tag}
                  </span>
                </div>
                <div className="project-episodes" style={{ fontSize: '0.72rem', color: '#8c909f' }}>
                  {tmpl.desc}
                </div>
              </div>
              <div className="project-right">
                <PlusCircle size={14} color={tmpl.color} />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Tab 3: Real Live System Engine Status */}
      {activeTab === 'system' && (
        <div className="recent-projects-list" style={{ padding: '8px 12px' }}>
          {[
            { key: 'durable_db', label: 'Cơ Sở Dữ Liệu (DB)', desc: 'SQLite / aiosqlite persistent engine' },
            { key: 'studio_orchestration', label: 'Orchestrator', desc: 'Studio run authority & DAG' },
            { key: 'story_engine', label: 'Story Engine', desc: 'Writer, Ideation & Outline engine' },
            { key: 'worker', label: 'Worker Swarm', desc: 'Durable execution worker heartbeat' },
            { key: 'model_route', label: 'Model Router', desc: 'Provider routing & token balancing' },
          ].map((item) => {
            const rawStatus = capabilities[item.key] || 'CHECKING';
            const isOk = rawStatus === 'AVAILABLE' || rawStatus === 'READY';
            return (
              <div
                key={item.key}
                style={{
                  padding: '10px 12px',
                  borderRadius: '10px',
                  background: 'rgba(255, 255, 255, 0.03)',
                  border: '1px solid rgba(255, 255, 255, 0.06)',
                  marginBottom: '8px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 700, color: '#ffffff' }}>{item.label}</span>
                  <span
                    style={{
                      fontSize: '0.68rem',
                      fontWeight: 700,
                      padding: '2px 6px',
                      borderRadius: '4px',
                      background: isOk ? 'rgba(78, 222, 163, 0.12)' : 'rgba(245, 158, 11, 0.12)',
                      color: isOk ? '#4edea3' : '#f59e0b',
                    }}
                  >
                    {rawStatus}
                  </span>
                </div>
                <span style={{ fontSize: '0.72rem', color: '#8c909f' }}>{item.desc}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Useful Links Section - Wired to real Navigation */}
      <div className="useful-links-section">
        <div className="useful-links-title">Lối Tắt Không Gian Làm Việc</div>
        <div className="useful-links-grid">
          <div className="link-item" onClick={() => handleLinkClick('#/system/workspace')} style={{ cursor: 'pointer' }}>
            <div className="link-icon">
              <Bot size={16} color="#4d8eff" />
            </div>
            <div className="link-text">
              <span className="link-label">Agent Workspace</span>
              <span className="link-desc">Multi-agent Swarm →</span>
            </div>
          </div>

          <div className="link-item" onClick={() => handleLinkClick('#/studio/characters')} style={{ cursor: 'pointer' }}>
            <div className="link-icon">
              <Users size={16} color="#4edea3" />
            </div>
            <div className="link-text">
              <span className="link-label">Nhân Vật (Cast)</span>
              <span className="link-desc">Hồ sơ nhân vật →</span>
            </div>
          </div>

          <div className="link-item" onClick={() => handleLinkClick('#/system/settings')} style={{ cursor: 'pointer' }}>
            <div className="link-icon">
              <Settings size={16} color="#c0c1ff" />
            </div>
            <div className="link-text">
              <span className="link-label">Cấu Hình Mô Hình</span>
              <span className="link-desc">Ollama & APIs →</span>
            </div>
          </div>

          <div className="link-item" onClick={() => handleLinkClick('#/dashboard')} style={{ cursor: 'pointer' }}>
            <div className="link-icon">
              <Activity size={16} color="#f59e0b" />
            </div>
            <div className="link-text">
              <span className="link-label">Bảng Điều Khiển</span>
              <span className="link-desc">Hiệu suất Studio →</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
};

export default StudioRightPanel;
