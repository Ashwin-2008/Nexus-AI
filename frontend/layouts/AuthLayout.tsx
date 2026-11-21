import React from 'react'
import { Link, Outlet } from 'react-router-dom'
import { BrainCircuit, FileSearch, LockKeyhole, Sparkles, ShieldCheck, Zap } from 'lucide-react'
import { OrbitalVisual, ThemeToggle } from '@/components/nx'

export default function AuthLayout() {
  return (
    <>
      <div className="nx-app-bg" aria-hidden="true">
        <div className="nx-grid-bg" />
        <div className="nx-aurora nx-aurora--one" />
        <div className="nx-aurora nx-aurora--two" />
        <div className="nx-aurora nx-aurora--three" />
      </div>

      <div className="nx-auth">
        <section className="nx-auth__visual">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, position: 'relative', zIndex: 2 }}>
            <span className="nx-logo-mark">
              <Sparkles size={20} strokeWidth={2.4} />
            </span>
            <div>
              <p className="nx-brand__name" style={{ fontSize: 15 }}>NEXUS AI</p>
              <p className="nx-brand__sub">Enterprise knowledge intelligence</p>
            </div>
          </div>

          <div className="nx-auth__hero nx-rise">
            <span className="nx-eyebrow">Grounded intelligence</span>
            <h1 className="nx-auth__headline">
              Your organization&apos;s
              <br />
              knowledge, <span>alive.</span>
            </h1>
            <p className="nx-auth__lead">
              A secure, evidence-first AI workspace that connects every source, retrieves the right context,
              and answers with citations you can verify.
            </p>
            <div className="nx-auth__pills">
              <span className="nx-badge nx-badge--info">Hybrid retrieval</span>
              <span className="nx-badge nx-badge--violet">Grounded citations</span>
              <span className="nx-badge nx-badge--success">Org-isolated</span>
            </div>
            <div className="nx-auth__features">
              <div className="nx-auth__feature">
                <BrainCircuit />
                <p>One reasoning layer</p>
                <span>Shared RAG across every specialist agent</span>
              </div>
              <div className="nx-auth__feature">
                <FileSearch />
                <p>Evidence first</p>
                <span>Source spans and verification on every answer</span>
              </div>
              <div className="nx-auth__feature">
                <LockKeyhole />
                <p>Permission aware</p>
                <span>Document-level access enforced before generation</span>
              </div>
            </div>
          </div>

          <div style={{ position: 'absolute', right: '-60px', bottom: '8%', opacity: 0.32, zIndex: 1, pointerEvents: 'none' }}>
            <OrbitalVisual />
          </div>

          <div className="nx-row" style={{ position: 'relative', zIndex: 2, color: 'var(--nx-faint)', fontSize: 10 }}>
            <ShieldCheck size={13} />
            <span>Organization-scoped · RBAC · audited access</span>
            <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <Zap size={12} /> v0.9
            </span>
          </div>
        </section>

        <section className="nx-auth__panel">
          <div style={{ position: 'absolute', top: 18, right: 18 }}>
            <ThemeToggle compact />
          </div>
          <div className="nx-auth__form">
            <Outlet />
            <p className="nx-xs nx-muted" style={{ textAlign: 'center', marginTop: 18 }}>
              By continuing you agree to your organization&apos;s acceptable use and data policies.
            </p>
            <p className="nx-xs" style={{ textAlign: 'center', marginTop: 6 }}>
              <Link to="/" style={{ color: 'var(--nx-muted)' }}>← Back to sign in</Link>
            </p>
          </div>
        </section>
      </div>
    </>
  )
}
