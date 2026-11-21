import React, { useEffect, useState } from 'react'
import { Building2, CalendarDays, KeyRound, Mail, Save, ShieldCheck, UserRound } from 'lucide-react'
import { useAuth } from '@/src/auth'
import { changePassword, updateCurrentUser } from '@/src/api'
import { Badge, Field, PageHeader, StatusBadge, formatDate } from '@/components/nx'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

export default function UserProfile() {
  const { user, refreshUser } = useAuth()
  const [fullName, setFullName] = useState(user?.full_name ?? '')
  const [email, setEmail] = useState(user?.email ?? '')
  const [saving, setSaving] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileSaved, setProfileSaved] = useState(false)

  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)
  const [passwordSaved, setPasswordSaved] = useState(false)

  useEffect(() => {
    setFullName(user?.full_name ?? '')
    setEmail(user?.email ?? '')
  }, [user])

  async function saveProfile(event: React.FormEvent) {
    event.preventDefault()
    setProfileError(null)
    setProfileSaved(false)
    setSaving(true)
    try {
      await updateCurrentUser({ full_name: fullName.trim(), email: email.trim() })
      await refreshUser()
      setProfileSaved(true)
    } catch (error) {
      setProfileError(error instanceof Error ? error.message : 'Unable to update profile')
    } finally {
      setSaving(false)
    }
  }

  async function savePassword(event: React.FormEvent) {
    event.preventDefault()
    setPasswordError(null)
    setPasswordSaved(false)
    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match')
      return
    }
    setPasswordSaving(true)
    try {
      await changePassword(currentPassword, newPassword)
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setPasswordSaved(true)
    } catch (error) {
      setPasswordError(error instanceof Error ? error.message : 'Unable to change password')
    } finally {
      setPasswordSaving(false)
    }
  }

  const initials = (user?.full_name || user?.email || 'N').slice(0, 2).toUpperCase()

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Account"
        title="Profile & session"
        description="Manage the identity attached to your organization membership and rotate your password."
        actions={<Badge tone="info" dot>{user?.role || 'member'}</Badge>}
      />

      <div className="nx-grid nx-grid--sidebar">
        <div className="nx-stack">
          <Card title="Identity" subtitle="Changes are written to the backend and reflected across your session." glow="cyan">
            <form onSubmit={saveProfile} className="nx-stack" style={{ gap: 14 }}>
              <div className="nx-row" style={{ gap: 14 }}>
                <span className="nx-avatar" style={{ width: 58, height: 58, borderRadius: 18, fontSize: 18 }}>{initials}</span>
                <div>
                  <p style={{ margin: 0, fontSize: 16, fontWeight: 800 }}>{user?.full_name || 'Unnamed member'}</p>
                  <p className="nx-xs nx-muted" style={{ margin: '4px 0 0' }}>{user?.email}</p>
                  <div className="nx-row" style={{ marginTop: 7, gap: 6 }}>
                    <StatusBadge status={user?.is_active ? 'active' : 'disabled'} />
                    <Badge tone="violet">{user?.role || 'member'}</Badge>
                  </div>
                </div>
              </div>

              <div className="nx-divider" />

              <div className="nx-grid nx-grid--2">
                <Field label="Full name">
                  <div style={{ position: 'relative' }}>
                    <UserRound size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
                    <Input value={fullName} onChange={(event) => setFullName(event.target.value)} style={{ paddingLeft: 35 }} placeholder="Your name" />
                  </div>
                </Field>
                <Field label="Email" hint="Changing email changes your sign-in identity.">
                  <div style={{ position: 'relative' }}>
                    <Mail size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
                    <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} style={{ paddingLeft: 35 }} required />
                  </div>
                </Field>
              </div>

              {profileError && <div className="nx-error">{profileError}</div>}
              {profileSaved && <div className="nx-success">Profile updated.</div>}

              <div className="nx-row nx-row--between">
                <span className="nx-xs nx-muted">User ID <span className="nx-mono">{user?.id?.slice(0, 8)}…</span></span>
                <Button type="submit" loading={saving}>
                  <Save size={14} /> Save profile
                </Button>
              </div>
            </form>
          </Card>

          <Card title="Password" subtitle="Rotating your password revokes all refresh tokens for your account.">
            <form onSubmit={savePassword} className="nx-stack" style={{ gap: 14 }}>
              <Field label="Current password">
                <Input type="password" autoComplete="current-password" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} required />
              </Field>
              <div className="nx-grid nx-grid--2">
                <Field label="New password" hint="8+ characters with upper/lower case and a number.">
                  <Input type="password" autoComplete="new-password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required />
                </Field>
                <Field label="Confirm new password">
                  <Input type="password" autoComplete="new-password" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} required />
                </Field>
              </div>

              {passwordError && <div className="nx-error">{passwordError}</div>}
              {passwordSaved && <div className="nx-success">Password updated. Other sessions have been revoked.</div>}

              <div className="nx-row nx-row--between">
                <span className="nx-xs nx-muted">A successful change signs out other devices.</span>
                <Button type="submit" variant="secondary" loading={passwordSaving}>
                  <KeyRound size={14} /> Change password
                </Button>
              </div>
            </form>
          </Card>
        </div>

        <div className="nx-stack">
          <Card title="Membership" subtitle="Organization-scoped access">
            <div className="nx-stack" style={{ gap: 12 }}>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><Building2 /></span>
                <div className="nx-list-item__body">
                  <p className="nx-list-item__title">Organization</p>
                  <p className="nx-list-item__sub nx-mono">{user?.organization_id}</p>
                </div>
              </div>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><ShieldCheck /></span>
                <div className="nx-list-item__body">
                  <p className="nx-list-item__title">Role</p>
                  <p className="nx-list-item__sub">{user?.role || 'member'}</p>
                </div>
              </div>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><CalendarDays /></span>
                <div className="nx-list-item__body">
                  <p className="nx-list-item__title">Member since</p>
                  <p className="nx-list-item__sub">{formatDate(user?.created_at)}</p>
                </div>
              </div>
            </div>
          </Card>

          <Card title="Session security" subtitle="Bearer token stored in session storage">
            <div className="nx-timeline">
              <div className="nx-timeline__item">
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Authenticated</p>
                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>
                  Access token is present for this tab and is cleared when it closes.
                </p>
              </div>
              <div className="nx-timeline__item">
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>401 handling</p>
                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>
                  Expired or revoked sessions automatically return to sign in.
                </p>
              </div>
              <div className="nx-timeline__item">
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Role checks</p>
                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>
                  Administrator-only surfaces are enforced by the API, not just hidden in the UI.
                </p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
