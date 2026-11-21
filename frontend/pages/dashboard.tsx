import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  ArrowRight,
  Bot,
  Database,
  FileStack,
  Gauge,
  MessageSquare,
  ScrollText,
  Search,
  ShieldAlert,
  Server,
  Sparkles,
  TrendingUp,
  Upload,
  Zap,
} from 'lucide-react'
import { useAuth } from '@/src/auth'
import {
  AgentExecution,
  AnalyticsOverview,
  DataSource,
  Document,
  analyticsOverview,
  health,
  listAgentExecutions,
  listDocuments,
  listSources,
} from '@/src/api'
import { Badge, EmptyState, PageHeader, StatCard, StatusBadge, cn, formatNumber, timeAgo } from '@/components/nx'
import { Card } from '@/components/ui/card'
import { Button } from '@/components/ui/button'

interface ServiceState {
  services: Record<string, string>
  status: string
}

function greeting(): string {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 18) return 'Good afternoon'
  return 'Good evening'
}

export default function Dashboard() {
  const { user } = useAuth()
  const [analytics, setAnalytics] = useState<AnalyticsOverview | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [sources, setSources] = useState<DataSource[]>([])
  const [executions, setExecutions] = useState<AgentExecution[]>([])
  const [serviceState, setServiceState] = useState<ServiceState | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([
      analyticsOverview(14),
      listDocuments(),
      listSources(),
      listAgentExecutions(6),
      health(),
    ]).then((results) => {
      if (cancelled) return
      const [analyticsResult, documentResult, sourceResult, executionResult, healthResult] = results
      if (analyticsResult.status === 'fulfilled') setAnalytics(analyticsResult.value)
      if (documentResult.status === 'fulfilled') setDocuments(documentResult.value)
      if (sourceResult.status === 'fulfilled') setSources(sourceResult.value)
      if (executionResult.status === 'fulfilled') setExecutions(executionResult.value)
      if (healthResult.status === 'fulfilled') setServiceState(healthResult.value)
      const failures = results.filter((result) => result.status === 'rejected')
      if (failures.length === results.length) setError('Unable to load dashboard data. Check that the API is reachable.')
      else if (failures.length > 0) setError(`${failures.length} dashboard data source${failures.length === 1 ? '' : 's'} could not be loaded.`)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const maxQueries = useMemo(
    () => Math.max(1, ...(analytics?.series.map((point) => point.queries) ?? [1])),
    [analytics],
  )
  const activeJobs = documents.filter((document) =>
    ['pending', 'processing'].includes(document.status) || ['queued', 'running', 'retrying'].includes(document.latest_job?.status ?? ''),
  ).length
  const completedDocuments = documents.filter((document) => document.status === 'completed').length
  const activeSources = sources.filter((source) => source.status === 'active').length
  const docStatus = analytics?.knowledge.documents_by_status ?? {}
  const totalStatus = Math.max(1, Object.values(docStatus).reduce((sum, value) => sum + value, 0))
  const services = serviceState?.services ?? {}
  const coreServices = ['api', 'database', 'storage', 'redis', 'qdrant', 'worker']
  const healthyCount = coreServices.filter((name) => services[name] === 'healthy').length

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow={`${greeting()}, ${(user?.full_name || 'there').split(' ')[0]}`}
        title={<>Your knowledge, <span className="nx-title--gradient">in motion.</span></>}
        description="Live organization telemetry, connected knowledge and specialist agents — all grounded in the same retrieval layer."
        actions={
          <>
            <Badge tone={serviceState?.status === 'healthy' ? 'success' : 'warning'} dot>
              {serviceState?.status ?? 'checking'}
            </Badge>
            <Link to="/app/rag"><Button variant="secondary"><Sparkles size={14} /> Ask Nexus</Button></Link>
          </>
        }
      />

      <section className="nx-hero nx-rise">
        <div className="nx-hero__copy">
          <span className="nx-eyebrow">Unified intelligence layer</span>
          <h2 className="nx-hero__title">
            Ask across every source.<br />
            <span>Trace every answer.</span>
          </h2>
          <p className="nx-hero__text">
            Nexus fuses dense and lexical retrieval, reranks evidence, checks permissions and verifies every
            citation before the answer reaches you.
          </p>
          <div className="nx-hero__actions">
            <Link to="/app/chat"><Button size="lg"><MessageSquare size={15} /> Open chat</Button></Link>
            <Link to="/app/rag"><Button variant="outline" size="lg"><Search size={15} /> Inspect retrieval</Button></Link>
            <Link to="/app/document-explorer"><Button variant="ghost" size="lg"><Upload size={15} /> Add documents</Button></Link>
          </div>
          <div className="nx-row" style={{ marginTop: 20, gap: 8 }}>
            <span className="nx-badge nx-badge--info">Hybrid RRF</span>
            <span className="nx-badge nx-badge--violet">Evidence revalidation</span>
            <span className="nx-badge nx-badge--success">Org-scoped</span>
          </div>
        </div>
        <div className="nx-hero__visual">
          <div style={{ position: 'relative', width: 250, height: 250 }}>
            <div style={{ position: 'absolute', inset: 0, borderRadius: '50%', border: '1px solid rgba(34,211,238,.24)', animation: 'nx-spin 18s linear infinite' }} />
            <div style={{ position: 'absolute', inset: 26, borderRadius: '50%', border: '1px solid rgba(139,92,246,.26)', animation: 'nx-spin-reverse 24s linear infinite' }} />
            <div style={{ position: 'absolute', inset: 58, borderRadius: '50%', border: '1px solid rgba(244,114,182,.2)', animation: 'nx-spin 12s linear infinite' }} />
            <div style={{ position: 'absolute', inset: '50% auto auto 50%', width: 78, height: 78, transform: 'translate(-50%,-50%) rotate(45deg)', borderRadius: 22, background: 'conic-gradient(from 210deg,#22d3ee,#818cf8,#f472b6,#22d3ee)', boxShadow: '0 0 48px rgba(34,211,238,.35)' }} />
            <span className="nx-orbital__satellite nx-orbital__satellite--one" style={{ top: '22%', right: '12%' }} />
            <span className="nx-orbital__satellite nx-orbital__satellite--two" style={{ bottom: '16%', left: '10%' }} />
          </div>
        </div>
      </section>

      {error && <div className="nx-error">{error}</div>}

      <section className="nx-grid nx-grid--4">
        <StatCard
          icon={<FileStack />}
          label="Documents"
          value={loading ? '—' : formatNumber(documents.length)}
          meta={`${completedDocuments} indexed · ${activeJobs} in flight`}
          progress={documents.length ? Math.round((completedDocuments / documents.length) * 100) : 0}
        />
        <StatCard
          icon={<Database />}
          label="Knowledge chunks"
          value={loading ? '—' : formatNumber(analytics?.knowledge.chunks ?? 0)}
          meta={`${formatNumber(activeSources)} active source${activeSources === 1 ? '' : 's'}`}
          accent="violet"
          progress={analytics?.knowledge.chunks ? 100 : 0}
        />
        <StatCard
          icon={<Zap />}
          label="Queries · 14 days"
          value={loading ? '—' : formatNumber(analytics?.queries.window ?? 0)}
          meta={analytics?.queries.avg_latency_ms ? `${Math.round(analytics.queries.avg_latency_ms)} ms avg latency` : 'No query telemetry yet'}
          accent="pink"
        />
        <StatCard
          icon={<Bot />}
          label="Agent runs"
          value={loading ? '—' : formatNumber(analytics?.agents.total ?? 0)}
          meta={analytics?.agents.avg_duration_ms ? `${Math.round(analytics.agents.avg_duration_ms)} ms avg duration` : 'No executions yet'}
          accent="green"
        />
      </section>

      <div className="nx-grid nx-grid--sidebar">
        <div className="nx-stack">
          <Card
            title="Query volume"
            subtitle="Organization retrieval traffic · last 14 days"
            actions={<Badge tone="info"><TrendingUp size={10} /> live telemetry</Badge>}
          >
            {loading ? (
              <div className="nx-skeleton" style={{ height: 170 }} />
            ) : analytics && analytics.series.some((point) => point.queries > 0) ? (
              <>
                <div className="nx-bars" style={{ height: 110 }}>
                  {analytics.series.map((point) => (
                    <span
                      key={point.date}
                      title={`${point.date}: ${point.queries} queries · ${point.avg_total_ms}ms`}
                      style={{
                        height: `${Math.max(4, (point.queries / maxQueries) * 100)}%`,
                        opacity: point.queries ? 0.85 : 0.22,
                      }}
                    />
                  ))}
                </div>
                <div className="nx-row nx-row--between" style={{ marginTop: 12 }}>
                  <span className="nx-xs nx-muted">{analytics.series[0]?.date}</span>
                  <span className="nx-xs nx-muted">{analytics.series[analytics.series.length - 1]?.date}</span>
                </div>
                <div className="nx-grid nx-grid--3" style={{ marginTop: 18, gap: 10 }}>
                  <div>
                    <p className="nx-xs nx-muted" style={{ margin: 0 }}>Success rate</p>
                    <p style={{ margin: '3px 0 0', fontSize: 20, fontWeight: 800 }}>
                      {analytics.queries.success_rate === null ? '—' : `${analytics.queries.success_rate}%`}
                    </p>
                  </div>
                  <div>
                    <p className="nx-xs nx-muted" style={{ margin: 0 }}>Average retrieval</p>
                    <p style={{ margin: '3px 0 0', fontSize: 20, fontWeight: 800 }}>
                      {analytics.queries.avg_retrieval_ms === null ? '—' : `${Math.round(analytics.queries.avg_retrieval_ms)}ms`}
                    </p>
                  </div>
                  <div>
                    <p className="nx-xs nx-muted" style={{ margin: 0 }}>P95 total</p>
                    <p style={{ margin: '3px 0 0', fontSize: 20, fontWeight: 800 }}>
                      {analytics.queries.p95_latency_ms === null ? '—' : `${Math.round(analytics.queries.p95_latency_ms)}ms`}
                    </p>
                  </div>
                </div>
              </>
            ) : (
              <EmptyState
                title="No query telemetry yet"
                description="Ask a question in chat or run a RAG query to populate retrieval analytics."
                icon={<Gauge />}
                action={<Link to="/app/chat"><Button size="sm">Start a conversation</Button></Link>}
              />
            )}
          </Card>

          <Card title="Recent documents" subtitle="Newest knowledge in your organization" actions={<Link to="/app/document-explorer" className="nx-xs" style={{ color: 'var(--nx-accent)' }}>View all <ArrowRight size={11} style={{ display: 'inline' }} /></Link>}>
            {loading ? (
              <div className="nx-stack"><div className="nx-skeleton" style={{ height: 44 }} /><div className="nx-skeleton" style={{ height: 44 }} /><div className="nx-skeleton" style={{ height: 44 }} /></div>
            ) : documents.length === 0 ? (
              <EmptyState title="No documents yet" description="Upload a file or connect a source to start building your knowledge base." icon={<Upload />} action={<Link to="/app/document-explorer"><Button size="sm">Upload a document</Button></Link>} />
            ) : (
              <div className="nx-list">
                {documents.slice(0, 5).map((document) => (
                  <div key={document.id} className="nx-list-item">
                    <span className="nx-list-item__icon"><FileStack /></span>
                    <div className="nx-list-item__body">
                      <p className="nx-list-item__title">{document.filename}</p>
                      <p className="nx-list-item__sub">{document.content_type || 'unknown type'} · updated {timeAgo(document.updated_at)}</p>
                    </div>
                    <StatusBadge status={document.status} />
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Recent agent activity" subtitle="Supervisor and specialist executions" actions={<Link to="/app/agent-control-center" className="nx-xs" style={{ color: 'var(--nx-accent)' }}>Open agents</Link>}>
            {loading ? (
              <div className="nx-skeleton" style={{ height: 100 }} />
            ) : executions.length === 0 ? (
              <EmptyState title="No agent runs" description="Delegate a multi-step task to the supervisor to see execution timelines here." icon={<Bot />} action={<Link to="/app/agent-control-center"><Button size="sm">Run a task</Button></Link>} />
            ) : (
              <div className="nx-timeline">
                {executions.slice(0, 5).map((execution) => (
                  <div key={execution.id} className="nx-timeline__item">
                    <div className="nx-row nx-row--between">
                      <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>{execution.request.slice(0, 80)}{execution.request.length > 80 ? '…' : ''}</p>
                      <StatusBadge status={execution.status} />
                    </div>
                    <p className="nx-xs nx-muted" style={{ margin: '4px 0 0' }}>
                      {execution.agent_type} · {timeAgo(execution.created_at)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="nx-stack">
          <Card title="Knowledge composition" subtitle="Indexed documents by status">
            <div className="nx-hbar">
              {['completed', 'processing', 'pending', 'failed'].map((status) => (
                <div key={status} className="nx-hbar__row">
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span className={cn('nx-dot', status === 'completed' ? 'nx-dot--success' : status === 'failed' ? 'nx-dot--danger' : 'nx-dot--warning')} />
                    {status}
                  </span>
                  <span className="nx-hbar__track">
                    <span className="nx-hbar__fill" style={{ width: `${Math.round(((docStatus[status] ?? 0) / totalStatus) * 100)}%`, opacity: status === 'completed' ? 1 : 0.6 }} />
                  </span>
                  <span className="nx-hbar__value">{docStatus[status] ?? 0}</span>
                </div>
              ))}
            </div>
            <div className="nx-divider" />
            <div className="nx-row nx-row--between">
              <span className="nx-xs nx-muted">Indexed documents</span>
              <span className="nx-small" style={{ fontWeight: 700 }}>{completedDocuments} / {documents.length}</span>
            </div>
            <div style={{ marginTop: 10 }} className="nx-hbar__track">
              <span className="nx-hbar__fill" style={{ width: `${documents.length ? (completedDocuments / documents.length) * 100 : 0}%` }} />
            </div>
          </Card>

          <Card title="Organization pulse" subtitle="Persisted activity across the workspace" actions={<Activity size={15} className="nx-muted" />}>
            <div className="nx-grid nx-grid--2" style={{ gap: 9 }}>
              <Link to="/app/chat" className="nx-list-item" style={{ color: 'inherit' }}>
                <span className="nx-list-item__icon"><MessageSquare /></span>
                <span className="nx-list-item__body"><span className="nx-list-item__title">Conversations</span><span className="nx-list-item__sub" style={{ fontSize: 17, fontWeight: 800, color: 'var(--nx-text)' }}>{formatNumber(analytics?.activity.conversations ?? 0)}</span></span>
              </Link>
              <Link to="/app/reports" className="nx-list-item" style={{ color: 'inherit' }}>
                <span className="nx-list-item__icon"><ScrollText /></span>
                <span className="nx-list-item__body"><span className="nx-list-item__title">Reports</span><span className="nx-list-item__sub" style={{ fontSize: 17, fontWeight: 800, color: 'var(--nx-text)' }}>{formatNumber(analytics?.activity.reports ?? 0)}</span></span>
              </Link>
              <Link to="/app/agent-control-center" className="nx-list-item" style={{ color: 'inherit' }}>
                <span className="nx-list-item__icon"><ShieldAlert /></span>
                <span className="nx-list-item__body"><span className="nx-list-item__title">Pending approvals</span><span className="nx-list-item__sub" style={{ fontSize: 17, fontWeight: 800, color: 'var(--nx-text)' }}>{formatNumber(analytics?.activity.pending_approvals ?? 0)}</span></span>
              </Link>
              <Link to="/app/document-explorer" className="nx-list-item" style={{ color: 'inherit' }}>
                <span className="nx-list-item__icon"><FileStack /></span>
                <span className="nx-list-item__body"><span className="nx-list-item__title">Ingestion in flight</span><span className="nx-list-item__sub" style={{ fontSize: 17, fontWeight: 800, color: 'var(--nx-text)' }}>{formatNumber(analytics?.activity.active_ingestions ?? activeJobs)}</span></span>
              </Link>
            </div>
          </Card>

          <Card title="Platform services" subtitle={`${healthyCount}/${coreServices.length} core services healthy`} actions={<Activity size={15} className="nx-muted" />}>
            <div className="nx-stack" style={{ gap: 8 }}>
              {coreServices.map((name) => {
                const value = services[name] ?? 'unknown'
                const healthy = value === 'healthy'
                return (
                  <div key={name} className="nx-row nx-row--between" style={{ padding: '7px 0', borderBottom: '1px solid var(--nx-border)' }}>
                    <span className="nx-row" style={{ gap: 8 }}>
                      <Server size={13} className="nx-muted" />
                      <span className="nx-small" style={{ textTransform: 'capitalize' }}>{name === 'api' ? 'API' : name}</span>
                    </span>
                    <Badge tone={healthy ? 'success' : value === 'unhealthy' ? 'danger' : 'warning'} dot>{value}</Badge>
                  </div>
                )
              })}
            </div>
            <Link to="/app/system-monitoring" className="nx-btn nx-btn--ghost nx-btn--sm nx-btn--block" style={{ marginTop: 12 }}>
              Open monitoring <ArrowRight size={13} />
            </Link>
          </Card>

          <Card title="Verification mix" subtitle="Answer verification outcomes in window">
            {analytics && Object.keys(analytics.distribution.verification).length > 0 ? (
              <div className="nx-hbar">
                {Object.entries(analytics.distribution.verification).map(([status, count]) => {
                  const total = Object.values(analytics.distribution.verification).reduce((sum, item) => sum + item, 0)
                  return (
                    <div key={status} className="nx-hbar__row">
                      <span style={{ textTransform: 'capitalize' }}>{status.replaceAll('_', ' ')}</span>
                      <span className="nx-hbar__track"><span className="nx-hbar__fill" style={{ width: `${Math.round((count / Math.max(1, total)) * 100)}%` }} /></span>
                      <span className="nx-hbar__value">{count}</span>
                    </div>
                  )
                })}
              </div>
            ) : (
              <EmptyState title="No verification data" description="Verification outcomes appear after grounded answers are generated." icon={<Sparkles />} />
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
