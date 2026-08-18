import React from 'react';
import { TitleCardState } from './types';

export interface TitleCardProps {
  state: TitleCardState;
}

export const TitleCard: React.FC<TitleCardProps> = ({ state }) => {
  return (
    <div className="layout-title">
      <div className="title-card-container">
        <div className="title-badge-row">
          <span className="badge-pill ep-badge">{state.badge}</span>
          <span className="badge-pill ver-badge">{state.version_tag}</span>
        </div>
        <h1 className="title-card-heading">{state.title}</h1>
        <p className="title-card-subheading">{state.subtitle}</p>
      </div>
    </div>
  );
};
