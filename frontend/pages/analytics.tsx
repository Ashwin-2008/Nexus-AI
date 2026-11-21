import React, { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  Bot,
  CheckCircle2,
  Clock3,
  FileStack,
  Gauge,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  TrendingUp,
} from 'lucide-react'
import { AnalyticsOverview, analyticsOverview } from '@/src/api'
import { Badge, EmptyState, PageHeader, StatCard, StatusBadge, formatNumber } from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Select } from '@/components/ui/input'

function Sparkline({ points }: { points: AnalyticsOverview['series'] }) {
  const max = Math.max(1, ...points.map((point) => point.queries))
  const width = 720
  const height = 180
  const step = points.length > 1 ? width / (points.length - 1) : width
  const coords = points.map((point, index) => ({
    x: index * step,
    y: height - 24 - (point.queries / max) * (height - 48),
  }))
  const line = coords.map((point) => `${point.x},${point.y}`).join(' ')
  const area = `0,${height} ${line} ${width},${height}`
  return (
    <div style={{ position: 'relative' }}>
      <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 190, overflow: 'visible' }} role="img" aria-label="Query volume trend">
        <defs>
          <linearGradient id="nx-area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--nx-accent)" stopOpacity="0.28" />
            <stop offset="100%" stopColor="var(--nx-accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line key={ratio} x1="0" y1={height * ratio} x2={width} y2={height * ratio} stroke="var(--nx-border)" strokeDasharray="4 6" />
        ))}
        <polygon points={area} fill="url(#nx-area)" />
        <polyline points={line} fill="none" stroke="var(--nx-accent)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {coords.map((point, index) => (
          <g key={index}>
            <circle cx={point.x} cy={point.y} r={points[index].queries ? 4 : 2.5} fill="var(--nx-surface-solid)" stroke="var(--nx-accent)" strokeWidth="2" />
            {points[index].queries > 0 && <title>{`${points[index].date}: ${points[index].queries} queries`}</title>}
          </g>
        ))}
      </svg>
      <div className="nx-row nx-row--between" style={{ marginTop: -8 }}>
        {points.filter((_, index) => index % Math.max(1, Math.round(points.length / 4)) === 0 || index === points.length - 1).map((point) => (
          <span key={point.date} className="nx-xs nx-muted">{point.date.slice(5)}</span>
        ))}
      </div>
    </div>
  )
}

function Distribution({ values, emptyLabel }: { values: Record<string, number>; emptyLabel: string }) {
  const entries = Object.entries(values).sort((a, b) => b[1] - a[1])
  const total = Math.max(1, entries.reduce((sum, [, value]) => sum + value, 0))
  if (!entries.length) return <p className="nx-xs nx-muted" style={{ margin: 0 }}>{emptyLabel}</p>
  return (
    <div className="nx-hbar">
      {entries.map(([key, value]) => (
        <div key={key} className="nx-hbar__row">
          <span style={{ textTransform: 'capitalize' }}>{key.replaceAll('_', ' ')}</span>
          <span className="nx-hbar__track"><span className="nx-hbar__fill" style={{ width: `${Math.round((value / total) * 100)}%` }} /></span>
          <span className="nx-hbar__value">{formatNumber(value)}</span>
        </div>
      ))}
    </div>
  )
}

export default function Analytics() {
  const [days, setDays] = useState(14)
  const [data, setData] = useState<AnalyticsOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function load(windowDays = days) {
    setLoading(true)
    setError(null)
    try {
      setData(await analyticsOverview(windowDays))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load analytics')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load(days)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days])

  const evaluationMetrics = useMemo(() => Object.entries(data?.evaluation.metrics ?? {}).filter(([, value]) => typeof value === 'number'), [data])
  const totalQueries = data?.queries.window ?? 0

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Observability"
        title="Analytics"
        description="Retrieval telemetry, verification outcomes, agent throughput and evaluation metrics — every value is derived from persisted organization data."
        actions={
          <>
            <Select value={days} onChange={(event) => setDays(Number(event.target.value))} style={{ width: 130 }}>
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
            </Select>
            <Button variant="secondary" onClick={() => void load(days)} loading={loading}><RefreshCw size={14} /> Refresh</Button>
          </>
        }
      />

      {error && <div className="nx-error">{error}</div>}

      <section className="nx-grid nx-grid--4">
        <StatCard icon={<Gauge />} label={`Queries · ${days}d`} value={loading ? '—' : formatNumber(totalQueries)} meta={data ? `${formatNumber(data.queries.total_all_time)} all time` : 'Loading telemetry'} />
        <StatCard icon={<CheckCircle2 />} label="Success rate" value={loading || data?.queries.success_rate == null ? '—' : `${data.queries.success_rate}%`} meta={data ? `${formatNumber(data.queries.successful)} answered · ${formatNumber(data.queries.no_evidence)} no evidence` : ''} accent="green" progress={data?.queries.success_rate ?? 0} />
        <StatCard icon={<Clock3 />} label="Avg latency" value={loading || data?.queries.avg_latency_ms == null ? '—' : `${Math.round(data.queries.avg_latency_ms)}ms`} meta={data?.queries.p95_latency_ms ? `P95 ${Math.round(data.queries.p95_latency_ms)}ms` : 'No latency samples'} accent="violet" />
        <StatCard icon={<FileStack />} label="Knowledge chunks" value={loading ? '—' : formatNumber(data?.knowledge.chunks ?? 0)} meta={data ? `${formatNumber(data.knowledge.active_sources)} active sources` : ''} accent="pink" />
      </section>

      <div className="nx-grid nx-grid--sidebar">
        <div className="nx-stack">
          <Card
            title="Query volume & latency"
            subtitle={`Organization retrieval traffic · last ${days} days`}
            actions={<Badge tone="info"><TrendingUp size={10} /> persisted telemetry</Badge>}
          >
            {loading ? (
              <div className="nx-skeleton" style={{ height: 210 }} />
            ) : totalQueries === 0 ? (
              <EmptyState icon={<BarChart3 />} title="No retrieval traffic in this window" description="Ask questions in chat or run RAG queries to populate this chart." />
            ) : (
              <>
                <Sparkline points={data?.series ?? []} />
                <div className="nx-grid nx-grid--3" style={{ marginTop: 16, gap: 10 }}>
                  <div className="nx-list-item">
                    <span className="nx-list-item__icon"><Gauge /></span>
                    <div className="nx-list-item__body"><p className="nx-list-item__title">Avg retrieval</p><p className="nx-list-item__sub">{data?.queries.avg_retrieval_ms == null ? '—' : `${Math.round(data.queries.avg_retrieval_ms)} ms`}</p></div>
                  </div>
                  <div className="nx-list-item">
                    <span className="nx-list-item__icon"><Clock3 /></span>
                    <div className="nx-list-item__body"><p className="nx-list-item__title">Avg end-to-end</p><p className="nx-list-item__sub">{data?.queries.avg_latency_ms == null ? '—' : `${Math.round(data.queries.avg_latency_ms)} ms`}</p></div>
                  </div>
                  <div className="nx-list-item">
                    <span className="nx-list-item__icon"><Sparkles /></span>
                    <div className="nx-list-item__body"><p className="nx-list-item__title">No-evidence</p><p className="nx-list-item__sub">{formatNumber(data?.queries.no_evidence ?? 0)} answers</p></div>
                  </div>
                </div>
              </>
            )}
          </Card>

          <div className="nx-grid nx-grid--2">
            <Card title="Answer modes" subtitle="How answers were produced">
              <Distribution values={data?.distribution.answer_modes ?? {}} emptyLabel="No answers in this window." />
            </Card>
            <Card title="Verification" subtitle="Evidence verification outcomes">
              <Distribution values={data?.distribution.verification ?? {}} emptyLabel="No verification results." />
            </Card>
          </div>

          <Card title="Agent throughput" subtitle="Supervisor and specialist executions">
            {loading ? <div className="nx-skeleton" style={{ height: 90 }} /> : (
              <>
                <div className="nx-row" style={{ gap: 10, marginBottom: 16 }}>
                  <Badge tone="info"><Bot size={10} /> {formatNumber(data?.agents.total ?? 0)} total runs</Badge>
                  {data?.agents.avg_duration_ms != null && <Badge tone="violet"><Clock3 size={10} /> {Math.round(data.agents.avg_duration_ms)} ms avg</Badge>}
                </div>
                <Distribution values={data?.agents.by_status ?? {}} emptyLabel="No agent executions recorded." />
              </>
            )}
          </Card>
        </div>

        <div className="nx-stack">
          <Card title="Knowledge health" subtitle="Document and chunk inventory">
            <div className="nx-ring" style={{ '--p': data ? (data.knowledge.documents_total ? Math.round(((data.knowledge.documents_by_status.completed ?? 0) / data.knowledge.documents_total) * 100) : 0) : 0 } as React.CSSProperties}>
              <span>{data?.knowledge.documents_total ? Math.round(((data.knowledge.documents_by_status.completed ?? 0) / data.knowledge.documents_total) * 100) : 0}%</span>
            </div>
            <p className="nx-xs nx-muted" style={{ textAlign: 'center', margin: '10px 0 16px' }}>documents indexed</p>
            <Distribution values={data?.knowledge.documents_by_status ?? {}} emptyLabel="No documents." />
            <div className="nx-divider" />
            <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Total chunks</span><span className="nx-small" style={{ fontWeight: 700 }}>{formatNumber(data?.knowledge.chunks ?? 0)}</span></div>
            <div className="nx-row nx-row--between" style={{ marginTop: 6 }}><span className="nx-xs nx-muted">Sources</span><span className="nx-small" style={{ fontWeight: 700 }}>{formatNumber(data?.knowledge.sources ?? 0)}</span></div>
          </Card>

          <Card title="Latest evaluation" subtitle="Persisted RAG evaluation run" actions={<ShieldCheck size={15} className="nx-muted" />}>
            {data?.evaluation.run_id ? (
              <div className="nx-stack" style={{ gap: 10 }}>
                <div className="nx-row nx-row--between">
                  <div>
                    <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>{data.evaluation.name}</p>
                    <p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>{data.evaluation.dataset} · {data.evaluation.item_count} items</p>
                  </div>
                  <StatusBadge status="completed" />
                </div>
                {evaluationMetrics.length > 0 ? (
                  <div className="nx-grid nx-grid--2" style={{ gap: 8 }}>
                    {evaluationMetrics.slice(0, 6).map(([key, value]) => (
                      <div key={key} className="nx-list-item" style={{ padding: 10 }}>
                        <div className="nx-list-item__body">
                          <p className="nx-list-item__title" style={{ textTransform: 'capitalize' }}>{key.replaceAll('_', ' ')}</p>
                          <p className="nx-list-item__sub" style={{ fontSize: 13, fontWeight: 800, color: 'var(--nx-text)' }}>{Number(value).toFixed(3)}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="nx-xs nx-muted" style={{ margin: 0 }}>This run persisted no numeric metrics.</p>
                )}
                <p className="nx-xs nx-muted nx-mono" style={{ margin: 0 }}>{data.evaluation.run_id}</p>
              </div>
            ) : (
              <EmptyState icon={<Activity />} title="No evaluation runs" description="Administrators can run a deterministic evaluation from the RAG API to measure retrieval quality." />
            )}
          </Card>

          <Card title="Retrieval modes" subtitle="Distribution of requested modes">
            <Distribution values={data?.distribution.retrieval_modes ?? {}} emptyLabel="No retrieval queries yet." />
          </Card>
        </div>
      </div>
    </div>
  )
}
