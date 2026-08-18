import React from 'react';
import { ChecklistState } from './types';

export interface ChecklistStageProps {
  state: ChecklistState;
}

export const ChecklistStage: React.FC<ChecklistStageProps> = ({ state }) => {
  return (
    <div className="layout-checklist">
      <div className="checklist-container">
        <h2 className="checklist-heading">{state.title}</h2>
        <p className="checklist-subheading">{state.subtitle}</p>
        <ul className="checklist-items">
          {state.items.map((item, idx) => {
            const isIncluded =
              item.status === 'INCLUDED' || item.status === 'DONE';
            return (
              <li
                key={idx}
                className={`checklist-row ${
                  isIncluded ? 'item-included' : 'item-excluded'
                }`}
              >
                <span className="check-icon">{isIncluded ? '✓' : '✗'}</span>
                <span className="check-text">{item.text}</span>
                {item.tag && <span className="item-tag">{item.tag}</span>}
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
};
