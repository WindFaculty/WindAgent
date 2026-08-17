/**
 * GlobalErrorBoundary — Top-level fatal error catching for App Root.
 */

import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class GlobalErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error('[GlobalErrorBoundary] Fatal application error:', error, errorInfo);
  }

  private handleReload = () => {
    window.location.hash = '#/dashboard';
    window.location.reload();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100vh',
            width: '100vw',
            backgroundColor: 'var(--studio-bg, #0b0f19)',
            color: 'var(--studio-text, #f1f5f9)',
            padding: '32px',
            fontFamily: 'var(--font-sans, system-ui, sans-serif)',
            textAlign: 'center',
          }}
        >
          <div
            style={{
              maxWidth: '540px',
              backgroundColor: 'var(--studio-surface, #131b2e)',
              border: '1px solid var(--studio-border, #1e293b)',
              borderRadius: '12px',
              padding: '32px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
            }}
          >
            <h2 style={{ fontSize: '20px', fontWeight: 600, margin: '0 0 12px 0', color: '#ef4444' }}>
              Application Critical Error
            </h2>
            <p style={{ fontSize: '14px', color: '#94a3b8', margin: '0 0 24px 0', lineHeight: 1.5 }}>
              {this.state.error?.message || 'An unexpected runtime error occurred.'}
            </p>
            <button
              onClick={this.handleReload}
              style={{
                backgroundColor: 'var(--color-primary, #3b82f6)',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                padding: '10px 20px',
                fontSize: '14px',
                fontWeight: 500,
                cursor: 'pointer',
              }}
            >
              Restart Application
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
