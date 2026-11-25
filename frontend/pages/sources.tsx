import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Braces,
  CheckCircle2,
  Cloud,
  Database,
  Github,
  Globe,
  Mail,
  Plug,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  Unplug,
  Waypoints,
} from 'lucide-react'
import {
  ConnectorType,
  DataSource,
  SyncJob,
  createSource,
  deleteSource,
  listSourceSyncs,
  listSources,
  syncSource,
  testSource,
} from '@/src/api'
import { EmptyState, Field, Modal, PageHeader, StatCard, StatusBadge, formatDate, timeAgo } from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/input'

const CONNECTORS: Array<{
  type: ConnectorType
  label: string
  description: string
  icon: React.ReactNode
  config: string
  credentials: string
}> = [
  {
    type: 'website',
    label: 'Website',
    description: 'Crawl an intranet or public site and ingest readable pages.',
    icon: <Globe />,
    config: `{
  "base_url": "https://docs.example.com",
  "max_pages": 25,
  "timeout_seconds": 15
}`,
    credentials: `{}`,
  },
  {
    type: 'postgres',
    label: 'PostgreSQL',
    description: 'Read rows from an allowed table with a read-only account.',
    icon: <Database />,
    config: `{
  "connection_url": "postgresql://db.internal:5432/knowledge",
  "query": "SELECT id, title, body AS content FROM articles",
  "max_rows": 100
}`,
    credentials: `{
  "username": "readonly",
  "password": ""
}`,
  },
  {
    type: 'mysql',
    label: 'MySQL',
    description: 'Sync structured records from a MySQL table.',
    icon: <Server />,
    config: `{
  "connection_url": "mysql://db.internal:3306/knowledge",
  "query": "SELECT id, title, body AS content FROM articles",
  "max_rows": 100
}`,
    credentials: `{
  "username": "readonly",
  "password": ""
}`,
  },
  {
    type: 'rest',
    label: 'REST API',
    description: 'Pull JSON records from a paginated HTTP endpoint.',
    icon: <Braces />,
    config: `{
  "url": "https://api.example.com/v1/articles",
  "item_path": "data",
  "title_field": "title",
  "text_fields": ["content", "description"],
  "page_size": 50,
  "max_pages": 4
}`,
    credentials: `{
  "token": ""
}`,
  },
  {
    type: 'github',
    label: 'GitHub',
    description: 'Index repository documentation and markdown files.',
    icon: <Github />,
    config: `{
  "repo": "your-org/knowledge-base",
  "branch": "main",
  "max_files": 50
}`,
    credentials: `{
  "token": ""
}`,
  },
  {
    type: 'gdrive',
    label: 'Google Drive',
    description: 'Sync shared documents from a Drive folder.',
    icon: <Cloud />,
    config: `{
  "folder_id": "drive-folder-id",
  "max_files": 25
}`,
    credentials: `{
  "client_id": "",
  "client_secret": "",
  "refresh_token": ""
}`,
  },
  {
    type: 'email',
    label: 'Email',
    description: 'Index mailboxes for grounded knowledge retrieval.',
    icon: <Mail />,
    config: `{
  "host": "imap.example.com",
  "port": 993,
  "folder": "INBOX",
  "use_ssl": true,
  "max_messages": 20,
  "smtp_host": "smtp.example.com",
  "smtp_port": 465,
  "smtp_ssl": true,
  "from_address": "support@example.com"
}`,
    credentials: `{
  "username": "support@example.com",
  "password": ""
}`,
  },
]

const SYNC_TERMINAL = new Set(['succeeded', 'partial', 'failed', 'cancelled'])

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function parseJson(value: string, label: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`)
  }
  return parsed as Record<string, unknown>
}

function connectorMeta(type: ConnectorType) {
  return CONNECTORS.find((item) => item.type === type) ?? CONNECTORS[0]
}

export default function KnowledgeSources() {
  const [sources, setSources] = useState<DataSource[]>([])
  const [selected, setSelected] = useState<DataSource | null>(null)
  const [syncs, setSyncs] = useState<SyncJob[]>([])
  const [syncLoading, setSyncLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [showCreate, setShowCreate] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [syncingId, setSyncingId] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const selectedIdRef = useRef<string | null>(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useEffect(() => {
    selectedIdRef.current = selected?.id ?? null
  }, [selected])

  const [name, setName] = useState('')
  const [type, setType] = useState<ConnectorType>('website')
  const [config, setConfig] = useState(CONNECTORS[0].config)
  const [credentials, setCredentials] = useState(CONNECTORS[0].credentials)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setSources(await listSources())
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load sources')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const counts = useMemo(
    () => ({
      total: sources.length,
      active: sources.filter((source) => source.status === 'active').length,
      error: sources.filter((source) => source.status === 'error').length,
      disabled: sources.filter((source) => source.status === 'disabled').length,
    }),
    [sources],
  )

  function chooseType(next: ConnectorType) {
    setType(next)
    const meta = connectorMeta(next)
    setConfig(meta.config)
    setCredentials(meta.credentials)
  }

  function openCreate() {
    setName('')
    chooseType('website')
    setShowCreate(true)
    setError(null)
    setMessage(null)
  }

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault()
    setCreating(true)
    setError(null)
    try {
      const source = await createSource(name.trim(), type, parseJson(config, 'Configuration'), parseJson(credentials, 'Credentials'))
      setSources((current) => [source, ...current])
      setShowCreate(false)
      setMessage(`${source.name} created. Test the connection before syncing.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to create source')
    } finally {
      setCreating(false)
    }
  }

  async function handleTest(source: DataSource) {
    setBusyId(source.id)
    setError(null)
    setMessage(null)
    try {
      const result = await testSource(source.id)
      if (!result.ok) throw new Error(result.error ?? 'Connection test failed')
      setMessage(`${source.name}: connection validated`)
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Connection test failed')
    } finally {
      setBusyId(null)
    }
  }

  async function handleSync(source: DataSource) {
    if (syncingId) return
    setSyncingId(source.id)
    setError(null)
    setMessage(null)
    const describe = (job: SyncJob) =>
      `${source.name}: ${job.status} · ${job.fetched} fetched · ${job.ingested} ingested · ${job.skipped} skipped · ${job.failed} failed`
    try {
      let job = await syncSource(source.id)
      setMessage(describe(job))
      // The API returns as soon as the job is queued/scheduled. Poll until the
      // job reaches a terminal state so counts never freeze at 0.
      let polls = 0
      while (mountedRef.current && !SYNC_TERMINAL.has(job.status) && polls < 240) {
        await sleep(1500)
        polls += 1
        const jobs = await listSourceSyncs(source.id)
        if (selectedIdRef.current === source.id) setSyncs(jobs)
        const current = jobs.find((item) => item.id === job.id)
        if (!current) break
        job = current
        if (polls % 4 === 0 || SYNC_TERMINAL.has(job.status)) setMessage(describe(job))
        if (polls === 20 && job.status === 'queued') {
          setMessage(`${source.name}: still queued — the sync has not started yet. If no Celery worker is deployed it will run in the API process.`)
        }
      }
      if (!mountedRef.current) return
      if (!SYNC_TERMINAL.has(job.status)) {
        setMessage(`${source.name}: ${job.status} — still running. Refresh later to see the final counts.`)
      } else if (job.error) {
        setMessage(describe(job))
        setError(job.error)
      } else {
        setMessage(describe(job))
      }
      await refresh()
      if (selectedIdRef.current === source.id) setSyncs(await listSourceSyncs(source.id))
    } catch (caught) {
      if (mountedRef.current) setError(caught instanceof Error ? caught.message : 'Sync failed')
    } finally {
      if (mountedRef.current) setSyncingId(null)
    }
  }

  async function handleSelect(source: DataSource) {
    setSelected(source)
    setSyncLoading(true)
    try {
      setSyncs(await listSourceSyncs(source.id))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load sync history')
    } finally {
      setSyncLoading(false)
    }
  }

  async function handleDelete(source: DataSource) {
    if (!window.confirm(`Disconnect ${source.name}? Connector-created documents will also be removed.`)) return
    setBusyId(source.id)
    try {
      await deleteSource(source.id)
      setSources((current) => current.filter((item) => item.id !== source.id))
      if (selected?.id === source.id) setSelected(null)
      setMessage(`${source.name} disconnected`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to disconnect source')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Knowledge fabric"
        title="Data sources"
        description="Connect websites, databases, repositories and mailboxes. Connector runs reuse the same validation, chunking and embedding pipeline as uploaded documents."
        actions={
          <>
            <Button variant="secondary" onClick={() => void refresh()} loading={loading}><RefreshCw size={14} /> Refresh</Button>
            <Button onClick={openCreate}><Plus size={14} /> Connect source</Button>
          </>
        }
      />

      <section className="nx-grid nx-grid--4">
        <StatCard icon={<Plug />} label="Connectors" value={counts.total} meta="Configured integrations" />
        <StatCard icon={<CheckCircle2 />} label="Active" value={counts.active} meta="Ready to synchronize" accent="green" />
        <StatCard icon={<Waypoints />} label="Errors" value={counts.error} meta="Need attention" accent="pink" />
        <StatCard icon={<Unplug />} label="Disabled" value={counts.disabled} meta="Paused connections" accent="violet" />
      </section>

      {error && <div className="nx-error">{error}</div>}
      {message && <div className="nx-success">{message}</div>}

      {loading ? (
        <div className="nx-grid nx-grid--3">
          {[1, 2, 3].map((key) => <div key={key} className="nx-skeleton" style={{ height: 190 }} />)}
        </div>
      ) : sources.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Plug />}
            title="No sources connected"
            description="Connect your first system to turn its content into searchable, permission-checked knowledge."
            action={<Button onClick={openCreate}><Plus size={14} /> Connect a source</Button>}
          />
        </Card>
      ) : (
        <div className="nx-grid nx-grid--3">
          {sources.map((source) => {
            const meta = connectorMeta(source.type)
            return (
              <article key={source.id} className="nx-card nx-card--hover" style={{ padding: 20 }}>
                <div className="nx-row nx-row--between" style={{ alignItems: 'flex-start' }}>
                  <span className="nx-stat__icon" style={{ width: 42, height: 42, borderRadius: 13 }}>{meta.icon}</span>
                  <StatusBadge status={source.status} />
                </div>
                <button type="button" onClick={() => void handleSelect(source)} style={{ border: 0, background: 'transparent', textAlign: 'left', padding: 0, marginTop: 14, color: 'inherit', width: '100%' }}>
                  <h3 style={{ margin: 0, fontSize: 15, fontWeight: 750 }}>{source.name}</h3>
                  <p className="nx-xs nx-muted" style={{ margin: '4px 0 0' }}>{meta.label} · {source.type}</p>
                </button>
                <p className="nx-xs nx-muted" style={{ margin: '12px 0 0', minHeight: 30, display: 'flex', alignItems: 'center', gap: 6 }}>
                  <RefreshCw size={11} />
                  {source.last_synced_at ? `Synced ${timeAgo(source.last_synced_at)}` : 'Never synchronized'}
                </p>
                {source.last_error && (
                  <p className="nx-xs" style={{ margin: '8px 0 0', color: 'var(--nx-danger)', lineHeight: 1.5 }}>
                    {source.last_error.slice(0, 120)}
                  </p>
                )}
                <div className="nx-row" style={{ marginTop: 16, gap: 7 }}>
                  <Button size="sm" variant="outline" onClick={() => void handleTest(source)} loading={busyId === source.id}>
                    Test
                  </Button>
                  <Button size="sm" onClick={() => void handleSync(source)} loading={syncingId === source.id} disabled={source.status === 'disabled' || Boolean(syncingId)}>
                    <RefreshCw size={12} /> Sync
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void handleSelect(source)}>
                    Details
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => void handleDelete(source)} style={{ marginLeft: 'auto', color: 'var(--nx-danger)' }} aria-label={`Disconnect ${source.name}`}>
                    <Trash2 size={13} />
                  </Button>
                </div>
              </article>
            )
          })}
        </div>
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Connect a knowledge source">
        <form onSubmit={handleCreate} className="nx-stack" style={{ gap: 14 }}>
          <div className="nx-grid nx-grid--2">
            <Field label="Connection name">
              <Input required placeholder="Engineering handbook" value={name} onChange={(event) => setName(event.target.value)} />
            </Field>
            <Field label="Connector type">
              <Select value={type} onChange={(event) => chooseType(event.target.value as ConnectorType)}>
                {CONNECTORS.map((connector) => <option key={connector.type} value={connector.type}>{connector.label}</option>)}
              </Select>
            </Field>
          </div>

          <p className="nx-xs nx-muted" style={{ margin: 0 }}>{connectorMeta(type).description}</p>

          <Field label="Configuration JSON" hint="Validated by the backend connector; keep secrets out of this object.">
            <Textarea value={config} onChange={(event) => setConfig(event.target.value)} spellCheck={false} style={{ fontFamily: 'monospace', fontSize: 11 }} />
          </Field>
          <Field label="Credentials JSON" hint="Encrypted at rest and never returned by the API.">
            <Textarea value={credentials} onChange={(event) => setCredentials(event.target.value)} spellCheck={false} style={{ fontFamily: 'monospace', fontSize: 11 }} />
          </Field>

          {error && <div className="nx-error">{error}</div>}

          <div className="nx-row nx-row--between">
            <span className="nx-xs nx-muted">Creation does not test connectivity. Use Test after saving.</span>
            <div className="nx-row" style={{ gap: 8 }}>
              <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>Cancel</Button>
              <Button type="submit" loading={creating}>Create source</Button>
            </div>
          </div>
        </form>
      </Modal>

      <Modal open={Boolean(selected)} onClose={() => setSelected(null)} title={selected ? `${selected.name} · ${connectorMeta(selected.type).label}` : 'Source detail'}>
        {selected && (
          <div className="nx-stack" style={{ gap: 16 }}>
            <div className="nx-row nx-row--between">
              <StatusBadge status={selected.status} />
              <span className="nx-xs nx-muted">Created {formatDate(selected.created_at)}</span>
            </div>

            <div className="nx-grid nx-grid--2" style={{ gap: 10 }}>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><RefreshCw /></span>
                <div className="nx-list-item__body">
                  <p className="nx-list-item__title">Last sync</p>
                  <p className="nx-list-item__sub">{selected.last_synced_at ? formatDate(selected.last_synced_at) : 'Never'}</p>
                </div>
              </div>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><CheckCircle2 /></span>
                <div className="nx-list-item__body">
                  <p className="nx-list-item__title">Last status</p>
                  <p className="nx-list-item__sub">{selected.last_sync_status || 'No runs recorded'}</p>
                </div>
              </div>
            </div>

            <details className="nx-details">
              <summary>Configuration</summary>
              <div><pre className="nx-code">{JSON.stringify(selected.config ?? {}, null, 2)}</pre></div>
            </details>
            <details className="nx-details">
              <summary>Masked credentials</summary>
              <div><pre className="nx-code">{JSON.stringify(selected.credentials_masked ?? {}, null, 2)}</pre></div>
            </details>

            <div>
              <p className="nx-label" style={{ marginBottom: 8 }}>Sync history</p>
              {syncLoading ? (
                <div className="nx-skeleton" style={{ height: 60 }} />
              ) : syncs.length === 0 ? (
                <p className="nx-xs nx-muted" style={{ margin: 0 }}>No sync runs recorded for this source.</p>
              ) : (
                <div className="nx-table__wrap">
                  <table className="nx-table">
                    <thead><tr><th>Status</th><th>Fetched</th><th>Ingested</th><th>Skipped</th><th>Failed</th><th>Started</th></tr></thead>
                    <tbody>
                      {syncs.map((job) => (
                        <tr key={job.id}>
                          <td>
                            <StatusBadge status={job.status} />
                            {job.error && (
                              <div className="nx-xs" style={{ color: 'var(--nx-danger)', marginTop: 4, maxWidth: 220 }} title={job.error}>
                                {job.error.slice(0, 100)}
                              </div>
                            )}
                          </td>
                          <td>{job.fetched}</td>
                          <td>{job.ingested}</td>
                          <td>{job.skipped}</td>
                          <td>{job.failed}</td>
                          <td className="nx-xs nx-muted">{formatDate(job.started_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {selected.last_error && <div className="nx-error">{selected.last_error}</div>}

            <div className="nx-row nx-row--between">
              <Button variant="ghost" onClick={() => void handleDelete(selected)} style={{ color: 'var(--nx-danger)' }}><Trash2 size={13} /> Disconnect</Button>
              <div className="nx-row" style={{ gap: 8 }}>
                <Button variant="outline" onClick={() => void handleTest(selected)} loading={busyId === selected.id}>Test connection</Button>
                <Button onClick={() => void handleSync(selected)} loading={syncingId === selected.id} disabled={Boolean(syncingId)}><RefreshCw size={13} /> Sync now</Button>
              </div>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
