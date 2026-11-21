import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck, Sparkles } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/nx'
import { useAuth } from '@/src/auth'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await login(email.trim(), password)
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to sign in')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="nx-card nx-card--glow nx-fade-in">
      <div className="nx-card__head">
        <div>
          <span className="nx-eyebrow">Welcome back</span>
          <h2 className="nx-title" style={{ fontSize: 28 }}>Sign in to Nexus</h2>
          <p className="nx-card__sub" style={{ marginTop: 8 }}>
            Access your organization&apos;s connected knowledge and specialist agents.
          </p>
        </div>
        <span className="nx-avatar" style={{ width: 42, height: 42 }}>
          <Sparkles size={18} />
        </span>
      </div>

      <form onSubmit={handleSubmit} className="nx-card__body nx-stack" style={{ gap: 15 }}>
        <Field label="Work email">
          <div style={{ position: 'relative' }}>
            <Mail size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
            <Input
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              style={{ paddingLeft: 35 }}
              required
            />
          </div>
        </Field>

        <Field label="Password">
          <div style={{ position: 'relative' }}>
            <LockKeyhole size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
            <Input
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              placeholder="Enter your password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              style={{ paddingLeft: 35, paddingRight: 42 }}
              required
            />
            <button
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? 'Hide password' : 'Show password'}
              style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', border: 0, background: 'transparent', color: 'var(--nx-muted)', display: 'grid', placeItems: 'center', width: 28, height: 28 }}
            >
              {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          </div>
        </Field>

        <div className="nx-row nx-row--between" style={{ marginTop: -2 }}>
          <span className="nx-xs nx-muted" style={{ display: 'inline-flex', gap: 5, alignItems: 'center' }}>
            <ShieldCheck size={12} /> Encrypted session
          </span>
          <Link to="/forgot-password" className="nx-xs" style={{ color: 'var(--nx-accent)' }}>
            Forgot password?
          </Link>
        </div>

        {error && <div className="nx-error" role="alert">{error}</div>}

        <Button type="submit" size="lg" loading={loading} className="nx-btn--block">
          {loading ? 'Signing in…' : 'Sign in'}
          {!loading && <ArrowRight size={15} />}
        </Button>

        <p className="nx-xs nx-muted" style={{ textAlign: 'center', margin: 0 }}>
          New to Nexus?{' '}
          <Link to="/register" style={{ color: 'var(--nx-accent)', fontWeight: 700 }}>
            Create an organization
          </Link>
        </p>
      </form>
    </div>
  )
}
