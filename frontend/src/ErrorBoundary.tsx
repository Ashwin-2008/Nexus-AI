import React from 'react'

interface ErrorBoundaryState {
  error: Error | null
}

export class ErrorBoundary extends React.Component<{ children: React.ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    // Surface the real failure in the browser console; never fabricate recovery.
    console.error('Nexus UI crashed', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <>
        <div className="nx-app-bg" aria-hidden="true">
          <div className="nx-grid-bg" />
        </div>
        <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24, position: 'relative', zIndex: 1 }}>
          <div className="nx-card nx-card--glow" style={{ width: 'min(100%, 560px)' }}>
            <div className="nx-card__body nx-stack" style={{ gap: 12 }}>
              <span className="nx-eyebrow">Interface error</span>
              <h1 className="nx-title" style={{ fontSize: 26 }}>Something went wrong</h1>
              <p className="nx-subtitle" style={{ marginTop: 0 }}>
                The interface hit an unexpected error. Your data has not been changed by this screen. Reload to try again.
              </p>
              <pre className="nx-code">{this.state.error.message}</pre>
              <div className="nx-row" style={{ gap: 8 }}>
                <button type="button" className="nx-btn nx-btn--primary" onClick={() => window.location.reload()}>
                  Reload interface
                </button>
                <button type="button" className="nx-btn nx-btn--ghost" onClick={() => this.setState({ error: null })}>
                  Try again
                </button>
              </div>
            </div>
          </div>
        </div>
      </>
    )
  }
}
