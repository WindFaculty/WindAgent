import React from 'react';
import { Alert, type AlertType } from './Alert';

export interface ToastProps {
  id: string;
  type?: AlertType;
  title?: string;
  message: string;
  onDismiss?: (id: string) => void;
}

export const Toast: React.FC<ToastProps> = ({
  id,
  type = 'info',
  title,
  message,
  onDismiss,
}) => {
  return (
    <div style={{ minWidth: 280, maxWidth: 420 }}>
      <Alert
        type={type}
        title={title}
        style={{ margin: 0, boxShadow: 'var(--shadow-lg)' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div>{message}</div>
          {onDismiss && (
            <button
              onClick={() => onDismiss(id)}
              style={{
                background: 'transparent',
                border: 'none',
                color: 'currentColor',
                cursor: 'pointer',
                marginLeft: 12,
                opacity: 0.7,
              }}
              aria-label="Dismiss toast"
            >
              &times;
            </button>
          )}
        </div>
      </Alert>
    </div>
  );
};

export default Toast;
