import React, { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Cpu,
  Database,
  HardDrive,
  Layers,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
  Wifi,
  WifiOff,
  Workflow,
} from 'lucide-react'
import { DataSource, Document, RagStatus, SystemCapabilities, health, listDocuments, listSources, ragStatus, systemCapabilities } from '@/src/api'
import { Badge, EmptyState, PageHeader, StatCard, StatusBadge, cn, formatDate, formatNumber, timeAgo } from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

interface HealthResult {
  status: string
  services: Record<string, string>
}

const SERVICE_LABELS: Record<string, string> = {
  api: 'API',
  database: 'PostgreSQL / database',
  redis: 'Redis / broker',
  qdrant: 'Qdrant vector store',
  storage: 'Object / local storage',
  worker: 'Celery worker',
}

const SERVICE_ICONS: Record<string, React.ReactNode> = {
  api: <Server />,
  database: <Database />,
  redis: <Workflow />,
  qdrant: <Layers />,
  storage: <HardDrive />,
  worker: <Activity />,
}

export default function SystemMonitoring() {
  const [healthState, setHealthState] = useState<HealthResult | null>(null)
  const [rag, setRag] = useState<RagStatus | null>(null)
  const [capabilities, setCapabilities] = useState<SystemCapabilities | null>(null)
  const [sources, setSources] = useState<DataSource[]>([])
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [probeMs, setProbeMs] = useState<number | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)

  async function probe() {
    setLoading(true)
    const started = performance.now()
    try {
      const result = await health()
      setProbeMs(Math.round(performance.now() - started))
      setHealthState(result)
      const [ragResult, sourceResult, documentResult, capabilityResult] = await Promise.allSettled([
        ragStatus(),
        listSources(),
        listDocuments(),
        systemCapabilities(),
      ])
      if (ragResult.status === 'fulfilled') setRag(ragResult.value)
      if (sourceResult.status === 'fulfilled') setSources(sourceResult.value)
      if (documentResult.status === 'fulfilled') setDocuments(documentResult.value)
      if (capabilityResult.status === 'fulfilled') setCapabilities(capabilityResult.value)
      setError(null)
    } catch (caught) {
      setHealthState(null)
      setProbeMs(null)
      setError(caught instanceof Error ? caught.message : 'Unable to reach the health endpoint')
    } finally {
      setCheckedAt(new Date())
      setLoading(false)
    }
  }

  useEffect(() => {
    void probe()
    const timer = window.setInterval(() => void probe(), 20000)
    return () => window.clearInterval(timer)
  }, [])

  const services = healthState?.services ?? {}
  const serviceNames = ['api', 'database', 'storage', 'redis', 'qdrant', 'worker']
  const healthy = serviceNames.filter((name) => services[name] === 'healthy').length
  const pendingDocuments = documents.filter((document) => ['pending', 'processing'].includes(document.status)).length
  const failedDocuments = documents.filter((document) => document.status === 'failed').length
  const failingSources = sources.filter((source) => source.status === 'error')
  const vector = (rag?.index.vector ?? {}) as Record<string, unknown>
  const chunks = rag?.documents.chunks ?? 0

  const connectorsByType = useMemo(() => {
    const result: Record<string, { total: number; active: number; errors: number }> = {}
    for (const source of sources) {
      const bucket = result[source.type] ?? { total: 0, active: 0, errors: 0 }
      bucket.total += 1
      if (source.status === 'active') bucket.active += 1
      if (source.status === 'error') bucket.errors += 1
      result[source.type] = bucket
    }
    return result
  }, [sources])

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Observability"
        title="System monitoring"
        description="Live service probes and persisted pipeline state. Optional infrastructure that is unavailable is reported as unhealthy rather than simulated."
        actions={
          <>
            <Badge tone={healthState?.status === 'healthy' ? 'success' : 'warning'} dot>{healthState?.status ?? 'unreachable'}</Badge>
            <Button variant="secondary" onClick={() => void probe()} loading={loading}><RefreshCw size={14} /> Probe now</Button>
          </>
        }
      />

      {error && <div className="nx-error">{error}</div>}

      <section className="nx-grid nx-grid--4">
        <StatCard icon={<ShieldCheck />} label="Healthy services" value={`${healthy}/${serviceNames.length}`} meta="Reported by /health" accent="green" progress={(healthy / serviceNames.length) * 100} />
        <StatCard icon={<Wifi />} label="API probe" value={probeMs === null ? '—' : `${probeMs}ms`} meta={checkedAt ? `checked ${checkedAt.toLocaleTimeString()}` : 'not checked'} accent="violet" />
        <StatCard icon={<Clock3 />} label="Awaiting ingestion" value={formatNumber(pendingDocuments)} meta={`${failedDocuments} failed documents`} accent={failedDocuments ? 'pink' : 'cyan'} />
        <StatCard icon={<Layers />} label="Vector points" value={formatNumber(chunks)} meta={`${String(vector.backend ?? 'unknown')} backend · ${String(vector.status ?? 'unknown')}`} />
      </section>

      <div className="nx-grid nx-grid--sidebar">
        <div className="nx-stack">
          <Card
            title="Service matrix"
            subtitle="Direct status returned by the backend health endpoint"
            actions={<Badge tone="info"><Activity size={10} /> auto-refresh 20s</Badge>}
            flush
          >
            <div className="nx-table__wrap" style={{ border: 0, borderRadius: 0, background: 'transparent' }}>
              <table className="nx-table">
                <thead><tr><th>Component</th><th>Status</th><th>Probe</th><th>Last check</th></tr></thead>
                <tbody>
                  {serviceNames.map((name) => {
                    const value = services[name] ?? 'unknown'
                    const isHealthy = value === 'healthy'
                    return (
                      <tr key={name}>
                        <td>
                          <span className="nx-row" style={{ gap: 9 }}>
                            <span className="nx-list-item__icon" style={{ width: 30, height: 30 }}>{SERVICE_ICONS[name]}</span>
                            <span className="nx-small" style={{ fontWeight: 700 }}>{SERVICE_LABELS[name]}</span>
                          </span>
                        </td>
                        <td><Badge tone={isHealthy ? 'success' : value === 'unhealthy' ? 'danger' : 'warning'} dot>{value}</Badge></td>
                        <td className="nx-xs nx-muted">{name === 'api' && probeMs !== null ? `${probeMs} ms` : 'reported status'}</td>
                        <td className="nx-xs nx-muted">{checkedAt ? checkedAt.toLocaleTimeString() : '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            <div style={{ padding: '0 22px 22px' }}>
              <div className="nx-row" style={{ gap: 7 }}>
                {services.redis === 'unhealthy' && <Badge tone="warning">Redis unavailable — Celery dispatch disabled</Badge>}
                {services.qdrant === 'unhealthy' && <Badge tone="warning">Qdrant unavailable — configured vector backend may be memory</Badge>}
                {services.worker === 'unhealthy' && <Badge tone="warning">Worker offline — ingestion runs in-process when enabled</Badge>}
              </div>
            </div>
          </Card>

          <Card title="Ingestion state" subtitle="Persisted document and index state" flush>
            <div style={{ padding: '0 22px 22px' }}>
              <div className="nx-grid nx-grid--3" style={{ gap: 10 }}>
                <div className="nx-list-item">
                  <span className="nx-list-item__icon"><Clock3 /></span>
                  <div className="nx-list-item__body"><p className="nx-list-item__title">Pending / processing</p><p className="nx-list-item__sub" style={{ fontSize: 17, fontWeight: 800, color: 'var(--nx-text)' }}>{pendingDocuments}</p></div>
                </div>
                <div className="nx-list-item">
                  <span className="nx-list-item__icon"><AlertTriangle /></span>
                  <div className="nx-list-item__body"><p className="nx-list-item__title">Failed documents</p><p className="nx-list-item__sub" style={{ fontSize: 17, fontWeight: 800, color: 'var(--nx-text)' }}>{failedDocuments}</p></div>
                </div>
                <div className="nx-list-item">
                  <span className="nx-list-item__icon"><CheckCircle2 /></span>
                  <div className="nx-list-item__body"><p className="nx-list-item__title">Out of sync</p><p className="nx-list-item__sub" style={{ fontSize: 17, fontWeight: 800, color: 'var(--nx-text)' }}>{rag?.sync.out_of_sync.length ?? 0}</p></div>
                </div>
              </div>
              {failedDocuments > 0 && (
                <div className="nx-stack" style={{ gap: 7, marginTop: 12 }}>
                  {documents.filter((document) => document.status === 'failed').slice(0, 4).map((document) => (
                    <div key={document.id} className="nx-row nx-row--between" style={{ padding: '8px 10px', border: '1px solid var(--nx-border)', borderRadius: 10 }}>
                      <span className="nx-xs">{document.filename}</span>
                      <span className="nx-xs" style={{ color: 'var(--nx-danger)', maxWidth: '45%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{document.error_message}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </Card>

          <Card title="Connector health" subtitle="Configured source status by connector type">
            {Object.keys(connectorsByType).length === 0 ? (
              <EmptyState icon={<WifiOff />} title="No connectors configured" description="Connected source health appears here after a source is created." />
            ) : (
              <div className="nx-stack" style={{ gap: 9 }}>
                {Object.entries(connectorsByType).map(([type, counts]) => (
                  <div key={type} className="nx-row nx-row--between" style={{ padding: '8px 0', borderBottom: '1px solid var(--nx-border)' }}>
                    <span className="nx-row" style={{ gap: 8 }}>
                      <span className={cn('nx-dot', counts.errors ? 'nx-dot--danger' : counts.active ? 'nx-dot--success' : 'nx-dot--warning')} />
                      <span className="nx-small" style={{ textTransform: 'capitalize' }}>{type}</span>
                    </span>
                    <span className="nx-row" style={{ gap: 6 }}>
                      <Badge>{counts.total} total</Badge>
                      {counts.active > 0 && <Badge tone="success">{counts.active} active</Badge>}
                      {counts.errors > 0 && <Badge tone="danger">{counts.errors} errors</Badge>}
                    </span>
                  </div>
                ))}
              </div>
            )}
            {failingSources.length > 0 && (
              <div className="nx-error" style={{ marginTop: 12 }}>
                {failingSources.length} source{failingSources.length === 1 ? '' : 's'} in error: {failingSources.map((source) => source.name).join(', ')}
              </div>
            )}
          </Card>
        </div>

        <div className="nx-stack">
          <Card title="Vector index" subtitle="Shared index used by every retrieval path">
            <div className="nx-stack" style={{ gap: 9 }}>
              <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Backend</span><Badge tone="violet">{String(vector.backend ?? 'unknown')}</Badge></div>
              <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Status</span><StatusBadge status={String(vector.status ?? 'unknown')} /></div>
              <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Collection</span><span className="nx-xs nx-mono">{String(rag?.index.collection ?? '—')}</span></div>
              <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Chunks</span><span className="nx-xs">{formatNumber(chunks)}</span></div>
              <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Reranker</span><Badge>{rag?.capabilities.reranker ?? '—'}</Badge></div>
              <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Verification</span><Badge tone={rag?.capabilities.verification ? 'success' : 'warning'}>{rag?.capabilities.verification ? 'enabled' : 'disabled'}</Badge></div>
            </div>
            {Boolean(vector.error) && <div className="nx-error" style={{ marginTop: 10 }}>{String(vector.error)}</div>}
          </Card>

          <Card title="AI providers" subtitle="Secret-free runtime configuration" actions={<Cpu size={15} className="nx-muted" />}>
            {capabilities ? (
              <div className="nx-stack" style={{ gap: 10 }}>
                <div className="nx-list-item">
                  <span className="nx-list-item__icon"><Sparkles /></span>
                  <div className="nx-list-item__body">
                    <p className="nx-list-item__title">Language model</p>
                    <p className="nx-list-item__sub">{capabilities.providers.llm.model} � {capabilities.providers.llm.provider}</p>
                  </div>
                  <Badge tone={capabilities.providers.llm.available ? 'success' : 'warning'} dot>{capabilities.providers.llm.available ? 'configured' : 'fallback'}</Badge>
                </div>
                <div className="nx-list-item">
                  <span className="nx-list-item__icon"><Layers /></span>
                  <div className="nx-list-item__body">
                    <p className="nx-list-item__title">Embeddings</p>
                    <p className="nx-list-item__sub">{capabilities.providers.embeddings.provider} � {capabilities.providers.embeddings.model}</p>
                  </div>
                  <Badge tone={capabilities.providers.embeddings.semantic ? 'success' : 'warning'}>{capabilities.providers.embeddings.semantic ? 'semantic' : 'non-semantic'}</Badge>
                </div>
                <div className="nx-row nx-row--between">
                  <span className="nx-xs nx-muted">Vector backend</span>
                  <Badge tone="violet">{capabilities.providers.vector.backend}</Badge>
                </div>
                <div className="nx-row nx-row--between">
                  <span className="nx-xs nx-muted">Storage backend</span>
                  <Badge>{capabilities.providers.storage.backend}</Badge>
                </div>
                <div className="nx-row nx-row--between">
                  <span className="nx-xs nx-muted">Retrieval mode</span>
                  <Badge tone="info">{String(capabilities.retrieval.mode ?? '�')}</Badge>
                </div>
                <div className="nx-row nx-row--between">
                  <span className="nx-xs nx-muted">Celery dispatch</span>
                  <Badge tone={capabilities.worker.celery_enabled ? 'success' : 'warning'}>{capabilities.worker.celery_enabled ? 'enabled' : 'in-process'}</Badge>
                </div>
                {capabilities.warnings.length > 0 && <div className="nx-error">{capabilities.warnings.join(' � ')}</div>}
              </div>
            ) : (
              <p className="nx-xs nx-muted" style={{ margin: 0 }}>Provider capabilities could not be loaded.</p>
            )}
          </Card>

          <Card title="Source freshness" subtitle="Most recent connector syncs">
            {sources.length === 0 ? (
              <EmptyState icon={<Database />} title="No connected sources" description="Create a connector to monitor freshness." />
            ) : (
              <div className="nx-list">
                {sources.slice(0, 6).map((source) => (
                  <div key={source.id} className="nx-list-item">
                    <span className="nx-list-item__icon"><Database /></span>
                    <div className="nx-list-item__body">
                      <p className="nx-list-item__title">{source.name}</p>
                      <p className="nx-list-item__sub">{source.last_synced_at ? `synced ${timeAgo(source.last_synced_at)}` : 'never synced'} · {formatDate(source.last_synced_at)}</p>
                    </div>
                    <StatusBadge status={source.status} />
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Operational notes" subtitle="Truthful constraints of this deployment">
            <div className="nx-timeline">
              <div className="nx-timeline__item">
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Optional services degrade honestly</p>
                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>Redis, Qdrant and the worker can be unhealthy while the API and database remain available.</p>
              </div>
              <div className="nx-timeline__item">
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>No synthetic metrics</p>
                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>Queue length, throughput and latency are shown only when the backend records them.</p>
              </div>
              <div className="nx-timeline__item">
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Probe is a real request</p>
                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>The API latency shown is the measured round-trip of this browser&apos;s health request.</p>
              </div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
