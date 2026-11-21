import React from 'react'
import { ArrowUpRight, Inbox, Moon, Sun } from 'lucide-react'
import { useTheme } from '@/src/theme'

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

type Tone = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'violet'

export function Badge({
  children,
  tone = 'default',
  dot = false,
  className,
}: {
  children: React.ReactNode
  tone?: Tone
  dot?: boolean
  className?: string
}) {
  return (
    <span className={cn('nx-badge', tone !== 'default' && `nx-badge--${tone}`, className)}>
      {dot && <span className={cn('nx-dot', tone !== 'default' && `nx-dot--${tone}`)} />}
      {children}
    </span>
  )
}

export function StatusBadge({ status }: { status?: string | null }) {
  const value = (status ?? 'unknown').toLowerCase()
  const tone: Tone =
    /complete|success|healthy|ready|active|approved|published|indexed/.test(value)
      ? 'success'
      : /fail|error|reject|cancel|delete|unhealthy|critical/.test(value)
        ? 'danger'
        : /pending|queue|process|run|warn|degraded|review|wait/.test(value)
          ? 'warning'
          : 'default'
  return (
    <Badge tone={tone} dot>
      {status || 'unknown'}
    </Badge>
  )
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string
  title: React.ReactNode
  description?: string
  actions?: React.ReactNode
}) {
  return (
    <header className="nx-page-head nx-rise">
      <div className="nx-page-head__copy">
        {eyebrow && <p className="nx-eyebrow">{eyebrow}</p>}
        <h1 className="nx-title">{title}</h1>
        {description && <p className="nx-subtitle">{description}</p>}
      </div>
      {actions && <div className="nx-actions">{actions}</div>}
    </header>
  )
}

export function StatCard({
  icon,
  label,
  value,
  meta,
  progress,
  accent,
  href,
}: {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
  meta?: React.ReactNode
  progress?: number
  accent?: 'cyan' | 'violet' | 'pink' | 'green'
  href?: string
}) {
  const body = (
    <div className="nx-stat">
      <div className="nx-stat__top">
        <div
          className="nx-stat__icon"
          style={
            accent === 'violet'
              ? { color: 'var(--nx-accent-2)' }
              : accent === 'pink'
                ? { color: 'var(--nx-accent-3)' }
                : accent === 'green'
                  ? { color: 'var(--nx-success)' }
                  : undefined
          }
        >
          {icon}
        </div>
        {href && <ArrowUpRight size={15} className="nx-muted" />}
      </div>
      <p className="nx-stat__label">{label}</p>
      <p className="nx-stat__value">{value}</p>
      {meta && <p className="nx-stat__meta">{meta}</p>}
      {typeof progress === 'number' && (
        <div className="nx-stat__bar">
          <span style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
        </div>
      )}
    </div>
  )
  return href ? (
    <a href={href} className="block">
      {body}
    </a>
  ) : (
    body
  )
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string
  description?: string
  action?: React.ReactNode
  icon?: React.ReactNode
}) {
  return (
    <div className="nx-empty">
      <div className="nx-empty__icon">{icon ?? <Inbox />}</div>
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action && <div style={{ marginTop: 6 }}>{action}</div>}
    </div>
  )
}

export function Skeleton({ height = 16, width = '100%', radius = 9 }: { height?: number | string; width?: number | string; radius?: number }) {
  return <div className="nx-skeleton" style={{ height, width, borderRadius: radius }} />
}

export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggle } = useTheme()
  return (
    <button
      type="button"
      onClick={toggle}
      className={compact ? 'nx-icon-btn' : 'nx-btn nx-btn--outline nx-btn--sm'}
      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
    >
      {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
      {!compact && (theme === 'dark' ? 'Light' : 'Dark')}
    </button>
  )
}

export function OrbitalVisual({ className = '' }: { className?: string }) {
  return (
    <div className={cn('nx-orbital', className)} aria-hidden="true">
      <div className="nx-orbital__ring nx-orbital__ring--one">
        <span className="nx-orbital__node" />
      </div>
      <div className="nx-orbital__ring nx-orbital__ring--two">
        <span className="nx-orbital__node nx-orbital__node--violet" />
      </div>
      <div className="nx-orbital__ring nx-orbital__ring--three">
        <span className="nx-orbital__node nx-orbital__node--pink" />
      </div>
      <div className="nx-orbital__core" />
      <span className="nx-orbital__satellite nx-orbital__satellite--one" />
      <span className="nx-orbital__satellite nx-orbital__satellite--two" />
    </div>
  )
}

export function Modal({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  if (!open) return null
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 80,
        display: 'grid',
        placeItems: 'center',
        padding: 18,
        background: 'rgba(2, 6, 18, 0.62)',
        backdropFilter: 'blur(6px)',
      }}
    >
      <div className="nx-card nx-fade-in" style={{ width: 'min(100%, 620px)', maxHeight: '88vh', overflowY: 'auto' }}>
        <div className="nx-card__head">
          <h2 className="nx-card__title">{title}</h2>
          <button type="button" className="nx-btn nx-btn--ghost nx-btn--sm" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="nx-card__body">{children}</div>
        {footer && <div className="nx-card__body" style={{ paddingTop: 0 }}>{footer}</div>}
      </div>
    </div>
  )
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <label className="nx-field">
      <span className="nx-label">{label}</span>
      {children}
      {hint && <span className="nx-hint">{hint}</span>}
    </label>
  )
}

export function Progress({ value, color }: { value: number; color?: string }) {
  return (
    <div className="nx-stat__bar">
      <span style={{ width: `${Math.max(0, Math.min(100, value))}%`, background: color }} />
    </div>
  )
}

export function timeAgo(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const seconds = Math.round((Date.now() - date.getTime()) / 1000)
  if (seconds < 45) return 'just now'
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h ago`
  if (seconds < 604800) return `${Math.round(seconds / 86400)}d ago`
  return date.toLocaleDateString()
}

export function formatNumber(value?: number | null): string {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat().format(value)
}

export function formatDate(value?: string | null): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString()
}
