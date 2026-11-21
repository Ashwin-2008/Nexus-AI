import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowRight, Building2, CheckCircle2, Mail, ShieldCheck, UserRound } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/nx'
import { register } from '@/src/api'
import { useAuth } from '@/src/auth'

const PASSWORD_HINT = 'At least 8 characters, including upper and lower case and a number.'

export default function Register() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [organizationName, setOrganizationName] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { login } = useAuth()

  const passwordChecks = [
    { label: '8+ characters', valid: password.length >= 8 },
    { label: 'Upper & lower case', valid: /[a-z]/.test(password) && /[A-Z]/.test(password) },
    { label: 'A number', valid: /\d/.test(password) },
  ]

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    if (!passwordChecks.every((check) => check.valid)) {
      setError(PASSWORD_HINT)
      return
    }
    setLoading(true)
    try {
      await register(email.trim(), password, name.trim(), organizationName.trim())
      await login(email.trim(), password)
      navigate('/app', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to register')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="nx-card nx-card--violet nx-fade-in">
      <div className="nx-card__head">
        <div>
          <span className="nx-eyebrow">Get started</span>
          <h2 className="nx-title" style={{ fontSize: 28 }}>Create your workspace</h2>
          <p className="nx-card__sub" style={{ marginTop: 8 }}>
            You&apos;ll be the administrator of a new, isolated organization.
          </p>
        </div>
        <span className="nx-avatar" style={{ width: 42, height: 42 }}>
          <Building2 size={18} />
        </span>
      </div>

      <form onSubmit={handleSubmit} className="nx-card__body nx-stack" style={{ gap: 14 }}>
        <Field label="Organization name">
          <div style={{ position: 'relative' }}>
            <Building2 size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
            <Input
              placeholder="Acme Knowledge Corp"
              value={organizationName}
              onChange={(event) => setOrganizationName(event.target.value)}
              style={{ paddingLeft: 35 }}
              minLength={1}
              required
            />
          </div>
        </Field>

        <Field label="Your name">
          <div style={{ position: 'relative' }}>
            <UserRound size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
            <Input
              autoComplete="name"
              placeholder="Full name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              style={{ paddingLeft: 35 }}
              required
            />
          </div>
        </Field>

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

        <Field label="Password" hint={PASSWORD_HINT}>
          <Input
            type="password"
            autoComplete="new-password"
            placeholder="Create a strong password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </Field>

        <div className="nx-row" style={{ gap: 7 }}>
          {passwordChecks.map((check) => (
            <span
              key={check.label}
              className="nx-badge"
              style={
                check.valid
                  ? { color: 'var(--nx-success)', borderColor: 'rgba(52,211,153,.24)', background: 'rgba(52,211,153,.08)' }
                  : undefined
              }
            >
              <CheckCircle2 size={10} /> {check.label}
            </span>
          ))}
        </div>

        {error && <div className="nx-error" role="alert">{error}</div>}

        <Button type="submit" size="lg" loading={loading} className="nx-btn--block">
          {loading ? 'Creating workspace…' : 'Create workspace'}
          {!loading && <ArrowRight size={15} />}
        </Button>

        <p className="nx-xs nx-muted" style={{ textAlign: 'center', margin: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5 }}>
          <ShieldCheck size={12} /> Organization data is isolated and access-controlled.
        </p>

        <p className="nx-xs nx-muted" style={{ textAlign: 'center', margin: 0 }}>
          Already have an account?{' '}
          <Link to="/" style={{ color: 'var(--nx-accent)', fontWeight: 700 }}>Sign in</Link>
        </p>
      </form>
    </div>
  )
}
