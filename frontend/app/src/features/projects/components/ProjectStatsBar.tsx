/**
 * ProjectStatsBar — 4 stat cards.
 * Weekly deltas are computed from real created_at timestamps returned by the
 * API — no hardcoded numbers, no decorative fake trend charts.
 */

import React from 'react';
import { Folder, Film, CheckCircle2, Star } from 'lucide-react';

export interface ProjectStats {
  totalProjects: number;
  producing: number;
  completed: number;
  totalEpisodes: number;
  newProjectsThisWeek: number;
  lockedEpisodes: number;
}

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string | number;
  sub: string;
  subColor: string;
  iconBg: string;
  iconColor: string;
  borderColor: string;
}

const StatCard: React.FC<StatCardProps> = ({ icon, label, value, sub, subColor, iconBg, iconColor, borderColor }) => {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 0,
        background: 'linear-gradient(180deg, rgba(19,27,46,1) 0%, rgba(15,23,42,0.96) 100%)',
        border: `1px solid ${borderColor}`,
        borderRadius: '14px',
        padding: '14px 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '12px',
        boxShadow: '0 8px 24px rgba(0,0,0,0.35)',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0 }}>
        <div
          style={{
            width: '40px',
            height: '40px',
            borderRadius: '10px',
            background: iconBg,
            border: `1px solid ${borderColor}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: iconColor,
            boxShadow: `0 0 16px ${iconBg}`,
            flexShrink: 0,
          }}
        >
          {icon}
        </div>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 600, letterSpacing: '0.02em', whiteSpace: 'nowrap' }}>{label}</div>
          <div style={{ fontSize: '22px', fontWeight: 800, color: '#f1f5f9', lineHeight: 1.1, marginTop: '2px' }}>{value}</div>
          <div style={{ fontSize: '11px', color: subColor, fontWeight: 600, marginTop: '3px', whiteSpace: 'nowrap' }}>{sub}</div>
        </div>
      </div>
    </div>
  );
};

function isWithinLastDays(dateStr?: string | null, days = 7): boolean {
  if (!dateStr) return false;
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return false;
  return Date.now() - d.getTime() <= days * 24 * 60 * 60 * 1000;
}

export const ProjectStatsBar: React.FC<{ stats: ProjectStats }> = ({ stats }) => {
  const producingPct = stats.totalProjects ? Math.round((stats.producing / stats.totalProjects) * 100) : 0;
  const completedPct = stats.totalProjects ? Math.round((stats.completed / stats.totalProjects) * 100) : 0;

  return (
    <div
      className="stats-grid"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, minmax(0, 1fr))',
        gap: '12px',
        marginBottom: '16px',
      }}
    >
      <StatCard
        icon={<Folder size={18} />}
        label="Tổng Projects"
        value={stats.totalProjects}
        sub={
          stats.newProjectsThisWeek > 0
            ? `+${stats.newProjectsThisWeek} project mới trong 7 ngày`
            : 'Không có project mới trong 7 ngày'
        }
        subColor={stats.newProjectsThisWeek > 0 ? '#4ade80' : '#64748b'}
        iconBg="rgba(56,189,248,0.14)"
        iconColor="#38bdf8"
        borderColor="rgba(56,189,248,0.22)"
      />
      <StatCard
        icon={<Film size={18} />}
        label="Đang sản xuất"
        value={stats.producing}
        sub={`${producingPct}% tổng số project`}
        subColor="#94a3b8"
        iconBg="rgba(139,92,246,0.16)"
        iconColor="#a78bfa"
        borderColor="rgba(139,92,246,0.22)"
      />
      <StatCard
        icon={<CheckCircle2 size={18} />}
        label="Hoàn thành"
        value={stats.completed}
        sub={`${completedPct}% tổng số project`}
        subColor="#94a3b8"
        iconBg="rgba(16,185,129,0.16)"
        iconColor="#34d399"
        borderColor="rgba(16,185,129,0.22)"
      />
      <StatCard
        icon={<Star size={18} />}
        label="Tổng tập phim"
        value={stats.totalEpisodes}
        sub={`${stats.lockedEpisodes} tập đã khoá kịch bản`}
        subColor="#f59e0b"
        iconBg="rgba(251,191,36,0.16)"
        iconColor="#fbbf24"
        borderColor="rgba(251,191,36,0.22)"
      />
    </div>
  );
};

/** Aggregate real stats from API-loaded projects (episodes carry DB states). */
export function computeProjectStats(projects: Array<{
  derived_status?: string;
  episodes_count?: number;
  created_at?: string | null;
  episodes?: Array<{ state?: string | null }>;
}>): ProjectStats {
  let producing = 0;
  let completed = 0;
  let totalEpisodes = 0;
  let newProjectsThisWeek = 0;
  let lockedEpisodes = 0;

  for (const p of projects) {
    if (p.derived_status === 'producing') producing++;
    if (p.derived_status === 'completed') completed++;
    totalEpisodes += p.episodes_count ?? 0;
    if (isWithinLastDays(p.created_at)) newProjectsThisWeek++;
    if (Array.isArray(p.episodes)) {
      for (const ep of p.episodes) {
        const s = (ep.state ?? '').toUpperCase();
        if (s === 'LOCKED' || s === 'READY_FOR_PRODUCTION') lockedEpisodes++;
      }
    }
  }

  return {
    totalProjects: projects.length,
    producing,
    completed,
    totalEpisodes,
    newProjectsThisWeek,
    lockedEpisodes,
  };
}
