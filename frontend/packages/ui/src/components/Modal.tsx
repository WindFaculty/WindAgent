import React, { useEffect, useRef } from 'react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: React.ReactNode;
  children: React.ReactNode;
  footer?: React.ReactNode;
  maxWidth?: string | number;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  footer,
  maxWidth = 560,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) {
        onClose();
      }
    };
    if (isOpen) {
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="ui-modal-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
    >
      <div
        ref={containerRef}
        className="ui-modal-container"
        style={{ maxWidth }}
        tabIndex={-1}
      >
        {title && (
          <div className="ui-panel__header">
            <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--studio-text-primary)' }}>
              {title}
            </div>
            <button
              onClick={onClose}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--studio-text-muted)',
                cursor: 'pointer',
                fontSize: '1.25rem',
                lineHeight: 1,
              }}
              aria-label="Close modal"
            >
              &times;
            </button>
          </div>
        )}
        <div className="ui-panel__content">{children}</div>
        {footer && <div className="ui-panel__footer">{footer}</div>}
      </div>
    </div>
  );
};

export const Dialog = Modal;
export default Modal;
