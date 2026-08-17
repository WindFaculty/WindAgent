/**
 * Phase 9A — CharactersPage
 * Canonical character catalog backed by /api/v3/projects/{id}/characters.
 * Zero DEFAULT_CHARACTERS — all data from backend.
 */
import React, { useState } from 'react';
import { useSearchParams } from '../../../shared/hooks/useSearchParams';
import { useCharacters, useCreateCharacter, useDeleteCharacter } from '../hooks/useCharacters';
import type { CharacterResource } from '@windagent/api-contracts';

interface CharactersPageProps {
  projectId: string;
}

export const CharactersPage: React.FC<CharactersPageProps> = ({ projectId }) => {
  const [searchParams, setSearchParams] = useSearchParams();
  const search = searchParams.get('search') ?? undefined;
  const [showCreateModal, setShowCreateModal] = useState(false);

  const { data: characters = [], isLoading, error } = useCharacters(projectId, search);
  const createMutation = useCreateCharacter(projectId);
  const deleteMutation = useDeleteCharacter(projectId);

  const [newCharForm, setNewCharForm] = useState({ name: '', role: 'Supporting', biography: '', dominant_trait: '', flaw: '' });

  const handleCreate = async () => {
    if (!newCharForm.name.trim()) return;
    await createMutation.mutateAsync(newCharForm);
    setNewCharForm({ name: '', role: 'Supporting', biography: '', dominant_trait: '', flaw: '' });
    setShowCreateModal(false);
  };

  if (isLoading) {
    return (
      <div className="characters-page characters-page--loading">
        <div className="loading-spinner" />
        <p>Đang tải danh sách nhân vật...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="characters-page characters-page--error">
        <h3>Không thể tải danh sách nhân vật</h3>
        <p>{(error as Error).message}</p>
      </div>
    );
  }

  return (
    <div className="characters-page">
      <header className="characters-page__header">
        <div className="characters-page__title-row">
          <h1>Nhân Vật</h1>
          <span className="characters-page__count">{characters.length} nhân vật</span>
        </div>

        <div className="characters-page__actions">
          <input
            type="search"
            className="characters-page__search"
            placeholder="Tìm kiếm nhân vật..."
            defaultValue={search}
            onChange={(e) => {
              const val = e.target.value;
              if (val) setSearchParams({ search: val });
              else setSearchParams({});
            }}
          />
          <button
            className="btn btn--primary"
            onClick={() => setShowCreateModal(true)}
          >
            + Thêm Nhân Vật
          </button>
        </div>
      </header>

      {characters.length === 0 ? (
        <div className="characters-page__empty">
          <span className="characters-page__empty-icon">🎭</span>
          <h3>Chưa có nhân vật nào</h3>
          <p>Bắt đầu xây dựng thế giới của bạn bằng cách thêm nhân vật đầu tiên.</p>
          <button className="btn btn--primary" onClick={() => setShowCreateModal(true)}>
            Thêm Nhân Vật Đầu Tiên
          </button>
        </div>
      ) : (
        <div className="characters-page__grid">
          {characters.map((char) => (
            <CharacterCard
              key={char.id}
              character={char}
              onDelete={() => deleteMutation.mutate(char.id)}
            />
          ))}
        </div>
      )}

      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal characters-page__create-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Tạo Nhân Vật Mới</h2>

            <div className="form-group">
              <label>Tên nhân vật *</label>
              <input
                className="form-input"
                value={newCharForm.name}
                onChange={(e) => setNewCharForm((f) => ({ ...f, name: e.target.value }))}
                placeholder="Tên nhân vật"
              />
            </div>

            <div className="form-group">
              <label>Vai trò</label>
              <select
                className="form-select"
                value={newCharForm.role}
                onChange={(e) => setNewCharForm((f) => ({ ...f, role: e.target.value }))}
              >
                <option value="Protagonist">Nhân vật chính</option>
                <option value="Antagonist">Nhân vật phản diện</option>
                <option value="Supporting">Nhân vật phụ</option>
                <option value="Draft">Nháp</option>
              </select>
            </div>

            <div className="form-group">
              <label>Tiểu sử</label>
              <textarea
                className="form-textarea"
                rows={3}
                value={newCharForm.biography}
                onChange={(e) => setNewCharForm((f) => ({ ...f, biography: e.target.value }))}
                placeholder="Mô tả nhân vật..."
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label>Tính cách nổi bật</label>
                <input
                  className="form-input"
                  value={newCharForm.dominant_trait}
                  onChange={(e) => setNewCharForm((f) => ({ ...f, dominant_trait: e.target.value }))}
                  placeholder="VD: Stoic, Chaotic..."
                />
              </div>
              <div className="form-group">
                <label>Điểm yếu</label>
                <input
                  className="form-input"
                  value={newCharForm.flaw}
                  onChange={(e) => setNewCharForm((f) => ({ ...f, flaw: e.target.value }))}
                  placeholder="VD: Impulsive..."
                />
              </div>
            </div>

            <div className="modal__actions">
              <button className="btn btn--ghost" onClick={() => setShowCreateModal(false)}>
                Hủy
              </button>
              <button
                className="btn btn--primary"
                disabled={!newCharForm.name.trim() || createMutation.isPending}
                onClick={handleCreate}
              >
                {createMutation.isPending ? 'Đang tạo...' : 'Tạo Nhân Vật'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

function CharacterCard({ character, onDelete }: { character: CharacterResource; onDelete: () => void }) {
  const roleColors: Record<string, string> = {
    Protagonist: '#22c55e',
    Antagonist: '#ef4444',
    Supporting: '#6366f1',
    Draft: '#6b7280',
  };

  const roleLabels: Record<string, string> = {
    Protagonist: 'Nhân vật chính',
    Antagonist: 'Phản diện',
    Supporting: 'Phụ',
    Draft: 'Nháp',
  };

  const role = character.identity.role;

  return (
    <div className="character-card">
      <div className="character-card__avatar">
        {character.identity.name.charAt(0)}
      </div>

      <div className="character-card__body">
        <div className="character-card__name-row">
          <h3 className="character-card__name">{character.identity.name}</h3>
          <span
            className="character-card__role-badge"
            style={{ backgroundColor: `${roleColors[role] ?? '#6b7280'}22`, color: roleColors[role] ?? '#6b7280', border: `1px solid ${roleColors[role] ?? '#6b7280'}44` }}
          >
            {roleLabels[role] ?? role}
          </span>
        </div>

        {character.psychology.dominant_trait && (
          <div className="character-card__traits">
            <span className="character-card__trait">{character.psychology.dominant_trait}</span>
            {character.psychology.flaw && <span className="character-card__trait character-card__trait--flaw">⚠ {character.psychology.flaw}</span>}
          </div>
        )}

        {character.identity.biography && (
          <p className="character-card__bio">{character.identity.biography.slice(0, 140)}{character.identity.biography.length > 140 ? '...' : ''}</p>
        )}

        <div className="character-card__meta">
          {character.voice_profile.voice_model_id && (
            <span className="character-card__meta-item">🎙 {character.voice_profile.voice_model_id}</span>
          )}
          {character.relationships.length > 0 && (
            <span className="character-card__meta-item">🔗 {character.relationships.length} liên kết</span>
          )}
          <span className="character-card__meta-item">v{character.version}</span>
        </div>
      </div>

      <div className="character-card__actions">
        <button
          className="character-card__action character-card__action--danger"
          onClick={onDelete}
          title="Xóa nhân vật"
        >
          🗑
        </button>
      </div>
    </div>
  );
}
