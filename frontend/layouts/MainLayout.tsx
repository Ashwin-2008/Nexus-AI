import React, { useEffect, useMemo, useState } from 'react'
import { Link, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Activity,
  BarChart3,
  Bell,
  Bot,
  ChevronRight,
  Database,
  FileStack,
  FileText,
  LayoutDashboard,
  Mail,
  LogOut,
  Menu,
  MessageSquare,
  Moon,
  Search,
  ShieldCheck,
  Sparkles,
  Sun,
  UserRound,
  X,
} from 'lucide-react'
import { useAuth } from '@/src/auth'
import { health } from '@/src/api'
import { useTheme } from '@/src/theme'
import { cn } from '@/components/nx'

interface NavItem {
  to: string
  label: string
  icon: React.ReactNode
}

interface NavSection {
  label: string
  items: NavItem[]
}

const ROUTE_META: Record<string, { eyebrow: string; title: string }> = {
  '/app': { eyebrow: 'Workspace', title: 'Command center' },
  '/app/chat': { eyebrow: 'Workspace', title: 'Intelligence chat' },
  '/app/search': { eyebrow: 'Knowledge', title: 'Federated search' },
  '/app/rag': { eyebrow: 'Knowledge', title: 'RAG operations' },
  '/app/knowledge-sources': { eyebrow: 'Knowledge', title: 'Data sources' },
  '/app/document-explorer': { eyebrow: 'Knowledge', title: 'Document explorer' },
  '/app/email': { eyebrow: 'Knowledge', title: 'Email intelligence' },
  '/app/database': { eyebrow: 'Knowledge', title: 'Database intelligence' },
  '/app/reports': { eyebrow: 'Operations', title: 'Reports' },
  '/app/agent-control-center': { eyebrow: 'Operations', title: 'Agent control center' },
  '/app/analytics': { eyebrow: 'Operations', title: 'Analytics' },
  '/app/system-monitoring': { eyebrow: 'Operations', title: 'System monitoring' },
  '/app/administration': { eyebrow: 'Organization', title: 'Administration' },
  '/app/profile': { eyebrow: 'Organization', title: 'Profile & session' },
}

export default function MainLayout() {
  const { user, logout } = useAuth()
  const { theme, toggle } = useTheme()
  const location = useLocation()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [apiStatus, setApiStatus] = useState<'checking' | 'online' | 'degraded' | 'offline'>('checking')
  const [serviceMap, setServiceMap] = useState<Record<string, string>>({})

  useEffect(() => {
    setOpen(false)
  }, [location.pathname])

  useEffect(() => {
    let cancelled = false
    const check = () => {
      health()
        .then((result) => {
          if (cancelled) return
          setServiceMap(result.services ?? {})
          setApiStatus(result.services?.api === 'unhealthy' ? 'offline' : result.status === 'healthy' ? 'online' : 'degraded')
        })
        .catch(() => !cancelled && setApiStatus('offline'))
    }
    check()
    const timer = window.setInterval(check, 30000)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        document.querySelector<HTMLInputElement>('[data-nexus-global-search]')?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const sections = useMemo<NavSection[]>(() => {
    const base: NavSection[] = [
      {
        label: 'Workspace',
        items: [
          { to: '/app', label: 'Dashboard', icon: <LayoutDashboard /> },
          { to: '/app/chat', label: 'Chat', icon: <MessageSquare /> },
          { to: '/app/search', label: 'Search', icon: <Search /> },
          { to: '/app/rag', label: 'RAG console', icon: <Sparkles /> },
        ],
      },
      {
        label: 'Knowledge',
        items: [
          { to: '/app/knowledge-sources', label: 'Sources', icon: <Database /> },
          { to: '/app/document-explorer', label: 'Documents', icon: <FileStack /> },
          { to: '/app/email', label: 'Email', icon: <Mail /> },
          { to: '/app/database', label: 'Database', icon: <Database /> },
        ],
      },
      {
        label: 'Operations',
        items: [
          { to: '/app/agent-control-center', label: 'Agents', icon: <Bot /> },
          { to: '/app/reports', label: 'Reports', icon: <FileText /> },
          { to: '/app/analytics', label: 'Analytics', icon: <BarChart3 /> },
          { to: '/app/system-monitoring', label: 'Monitoring', icon: <Activity /> },
        ],
      },
    ]
    const org: NavSection = {
      label: 'Organization',
      items: [{ to: '/app/profile', label: 'Profile', icon: <UserRound /> }],
    }
    if (user?.role === 'admin') {
      org.items.unshift({ to: '/app/administration', label: 'Administration', icon: <ShieldCheck /> })
    }
    return [...base, org]
  }, [user?.role])

  const meta = ROUTE_META[location.pathname] ?? { eyebrow: 'Nexus AI', title: 'Workspace' }
  const initials = (user?.full_name || user?.email || 'N').slice(0, 2).toUpperCase()

  function submitSearch(event: React.FormEvent) {
    event.preventDefault()
    const value = query.trim()
    if (!value) return
    navigate(`/app/search?q=${encodeURIComponent(value)}`)
    setQuery('')
  }

  return (
    <div className="nx-shell">
      <div className="nx-app-bg" aria-hidden="true">
        <div className="nx-grid-bg" />
        <div className="nx-aurora nx-aurora--one" />
        <div className="nx-aurora nx-aurora--two" />
        <div className="nx-aurora nx-aurora--three" />
      </div>

      {open && <button type="button" className="nx-mobile-overlay" onClick={() => setOpen(false)} aria-label="Close navigation" />}

      <aside className={cn('nx-sidebar', open && 'is-open')}>
        <Link to="/app" className="nx-brand" aria-label="Nexus AI home">
          <span className="nx-logo-mark">
            <Sparkles size={20} strokeWidth={2.4} />
          </span>
          <span>
            <p className="nx-brand__name">NEXUS AI</p>
            <p className="nx-brand__sub">Knowledge intelligence</p>
          </span>
        </Link>

        <nav className="nx-nav" aria-label="Primary navigation">
          {sections.map((section) => (
            <div key={section.label}>
              <p className="nx-nav__label">{section.label}</p>
              {section.items.map((item) => {
                const active =
                  location.pathname === item.to ||
                  (item.to !== '/app' && location.pathname.startsWith(`${item.to}/`))
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    aria-current={active ? 'page' : undefined}
                    className={cn('nx-nav-link', active && 'is-active')}
                  >
                    {item.icon}
                    <span>{item.label}</span>
                  </Link>
                )
              })}
            </div>
          ))}
        </nav>

        <div className="nx-sidebar__bottom">
          <div className="nx-status-card">
            <div className="nx-status-card__title">
              <span
                className={cn(
                  'nx-dot',
                  apiStatus === 'online' && 'nx-dot--success',
                  apiStatus === 'degraded' && 'nx-dot--warning',
                  (apiStatus === 'offline' || apiStatus === 'checking') && 'nx-dot--danger',
                )}
                style={{ animation: apiStatus === 'online' ? 'nx-pulse-glow 2.8s ease-in-out infinite' : undefined }}
              />
              Platform status
            </div>
            <p className="nx-status-card__value">
              {apiStatus === 'checking'
                ? 'Checking services'
                : apiStatus === 'online'
                  ? 'All core systems online'
                  : apiStatus === 'degraded'
                    ? 'API online · optional services degraded'
                    : 'API unreachable'}
            </p>
            <p className="nx-xs nx-muted" style={{ margin: '5px 0 0' }}>
              {serviceMap.database === 'healthy' ? 'Database connected' : 'Database status unknown'}
              {' · '}
              {serviceMap.storage === 'healthy' ? 'Storage ready' : 'Storage degraded'}
            </p>
          </div>

          <Link to="/app/profile" className="nx-sidebar-user" style={{ color: 'inherit' }}>
            <span className="nx-avatar">{initials}</span>
            <span style={{ minWidth: 0, flex: 1 }}>
              <span className="nx-small nx-truncate" style={{ display: 'block', fontWeight: 700 }}>
                {user?.full_name || 'Nexus member'}
              </span>
              <span className="nx-xs nx-muted nx-truncate" style={{ display: 'block' }}>
                {user?.email}
              </span>
            </span>
            <ChevronRight size={14} className="nx-muted" />
          </Link>
        </div>
      </aside>

      <div className="nx-main">
        <header className="nx-topbar">
          <button type="button" className="nx-icon-btn nx-mobile-only" onClick={() => setOpen((value) => !value)} aria-label="Toggle navigation">
            {open ? <X /> : <Menu />}
          </button>
          <div className="nx-topbar__route">
            <span className="nx-topbar__eyebrow">{meta.eyebrow}</span>
            <span className="nx-topbar__title">{meta.title}</span>
          </div>

          <form className="nx-topbar__search" onSubmit={submitSearch} role="search">
            <Search />
            <input
              data-nexus-global-search
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search your organization knowledge…"
              aria-label="Search knowledge"
            />
            <span className="nx-kbd">⌘K</span>
          </form>

          <button type="button" className="nx-icon-btn" onClick={toggle} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} title="Toggle theme">
            {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
          </button>
          <Link to="/app/system-monitoring" className="nx-icon-btn" aria-label="Service notifications" title="Service health">
            <Bell size={17} />
          </Link>
          <button type="button" className="nx-icon-btn" onClick={logout} aria-label="Sign out" title="Sign out">
            <LogOut size={16} />
          </button>
        </header>

        <main className="nx-content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
