import React from 'react';
import { UI_COLORS } from '../styles/uiTokens';

const isDevelopment = Boolean(import.meta.env?.DEV);

/**
 * ErrorBoundary - Catches React component errors and displays fallback UI
 * Prevents white screen crashes
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      errorCount: 0,
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    // Log error details for debugging
    console.error('ErrorBoundary caught:', error);
    console.error('Error details:', errorInfo);

    this.setState((prevState) => ({
      error,
      errorInfo,
      errorCount: prevState.errorCount + 1,
    }));

    // You can also log to an error reporting service here (Sentry, etc.)
    // logErrorToService(error, errorInfo);
  }

  handleReset = () => {
    this.setState({
      hasError: false,
      error: null,
      errorInfo: null,
    });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          role="alert"
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100dvh',
            backgroundColor: UI_COLORS.bg,
            color: UI_COLORS.textPrimary,
            padding: '20px',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          <div
            style={{
              maxWidth: '500px',
              padding: '40px',
              backgroundColor: UI_COLORS.surface,
              borderRadius: '8px',
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
              textAlign: 'center',
            }}
          >
            <h1 style={{ color: '#dc3545', marginBottom: '16px' }}>
              Warning: Something went wrong
            </h1>
            <p style={{ color: UI_COLORS.textSec, marginBottom: '24px', lineHeight: '1.6' }}>
              The application encountered an unexpected error. Please try refreshing the page or contact support if the problem persists.
            </p>

            {isDevelopment && this.state.error && (
              <details
                style={{
                  textAlign: 'left',
                  marginBottom: '24px',
                  padding: '12px',
                  backgroundColor: UI_COLORS.bg,
                  borderRadius: '4px',
                  border: `1px solid ${UI_COLORS.border}`,
                }}
              >
                <summary style={{ cursor: 'pointer', fontWeight: 'bold', marginBottom: '8px' }}>
                  Error Details (Development Only)
                </summary>
                <pre
                  style={{
                    fontSize: '12px',
                    overflow: 'auto',
                    backgroundColor: UI_COLORS.surface,
                    padding: '8px',
                    borderRadius: '4px',
                    border: `1px solid ${UI_COLORS.border}`,
                  }}
                >
                  {this.state.error.toString()}
                  {'\n\n'}
                  {this.state.errorInfo?.componentStack}
                </pre>
              </details>
            )}

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
              <button
                type="button"
                onClick={this.handleReset}
                style={{
                  padding: '10px 24px',
                  backgroundColor: '#005a9c',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '14px',
                }}
              >
                Try Again
              </button>
              <button
                type="button"
                onClick={() => { window.location.assign('#/home'); }}
                style={{
                  padding: '10px 24px',
                  backgroundColor: '#6c757d',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: '600',
                  fontSize: '14px',
                }}
              >
                Go Home
              </button>
            </div>

            {this.state.errorCount > 2 && (
              <p style={{ color: '#dc3545', marginTop: '24px', fontSize: '12px' }}>
                Multiple errors detected. Please refresh the page completely or clear your browser cache.
              </p>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
