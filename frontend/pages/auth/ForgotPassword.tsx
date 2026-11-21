import React, { useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, LifeBuoy, Mail, ShieldAlert } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Field } from '@/components/nx'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setSubmitted(true)
  }

  return (
    <div className="nx-card nx-fade-in">
      <div className="nx-card__head">
        <div>
          <span className="nx-eyebrow">Account recovery</span>
          <h2 className="nx-title" style={{ fontSize: 27 }}>Reset access</h2>
          <p className="nx-card__sub" style={{ marginTop: 8 }}>
            Nexus does not currently operate a self-service email reset service on this deployment.
          </p>
        </div>
        <span className="nx-avatar" style={{ width: 42, height: 42 }}>
          <LifeBuoy size={18} />
        </span>
      </div>

      <form onSubmit={handleSubmit} className="nx-card__body nx-stack" style={{ gap: 15 }}>
        <div className="nx-error" style={{ color: 'var(--nx-warning)', borderColor: 'rgba(251,191,36,.28)', background: 'rgba(251,191,36,.07)' }}>
          <ShieldAlert size={15} />
          <span>
            Password recovery requires an administrator or your identity provider. No recovery email is sent from this deployment.
          </span>
        </div>

        <Field label="Work email" hint="Used only to identify your organization so support can verify the request.">
          <div style={{ position: 'relative' }}>
            <Mail size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
            <Input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
              style={{ paddingLeft: 35 }}
              required
            />
          </div>
        </Field>

        {submitted && (
          <div className="nx-success">
            Request noted for this session. Contact your organization administrator and reference the email <strong>{email}</strong>. An administrator can rotate your credentials from the identity provider or backend operator console.
          </div>
        )}

        <Button type="submit" className="nx-btn--block" size="lg">
          Show recovery guidance
        </Button>

        <Link to="/" className="nx-btn nx-btn--ghost nx-btn--sm nx-btn--block">
          <ArrowLeft size={14} /> Back to sign in
        </Link>
      </form>
    </div>
  )
}
