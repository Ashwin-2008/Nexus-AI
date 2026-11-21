import React from 'react'
import { Card, Button, Input } from '@/components/ui'
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

const connectorTypes: ConnectorType[] = ['postgres', 'mysql', 'rest', 'website', 'github', 'gdrive', 'email']

function parseJson(value: string, label: string): Record<string, unknown> {
  const parsed: unknown = JSON.parse(value)
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
    throw new Error(`${label} must be a JSON object`)
  }
  return parsed as Record<string, unknown>
}

export default function KnowledgeSources() {
  const [sources, setSources] = React.useState<DataSource[]>([])
  const [selected, setSelected] = React.useState<DataSource | null>(null)
  const [syncs, setSyncs] = React.useState<SyncJob[]>([])
  const [name, setName] = React.useState('')
  const [type, setType] = React.useState<ConnectorType>('website')
  const [config, setConfig] = React.useState('{}')
  const [credentials, setCredentials] = React.useState('{}')
  const [loading, setLoading] = React.useState(true)
  const [saving, setSaving] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [message, setMessage] = React.useState<string | null>(null)

  const refresh = React.useCallback(async () => {
    setLoading(true)
    try {
      setSources(await listSources())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load sources')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { void refresh() }, [refresh])

  async function handleCreate(event: React.FormEvent) {
    event.preventDefault()
    setSaving(true)
    try {
      const source = await createSource(name.trim(), type, parseJson(config, 'Config'), parseJson(credentials, 'Credentials'))
      setSources((current) => [source, ...current])
      setName('')
      setConfig('{}')
      setCredentials('{}')
      setMessage('Source created. Test the connection before syncing.')
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to create source')
    } finally {
      setSaving(false)
    }
  }

  async function handleTest(source: DataSource) {
    setMessage(null)
    try {
      const result = await testSource(source.id)
      if (!result.ok) throw new Error(result.error ?? 'Connection test failed')
      setMessage(`${source.name}: connection validated`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Connection test failed')
    }
  }

  async function handleSync(source: DataSource) {
    setMessage(null)
    try {
      const job = await syncSource(source.id)
      setMessage(`${source.name}: sync ${job.status} (${job.ingested} ingested, ${job.skipped} skipped)`)
      await refresh()
      if (selected?.id === source.id) setSyncs(await listSourceSyncs(source.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Sync failed')
    }
  }

  async function handleSelect(source: DataSource) {
    setSelected(source)
    try {
      setSyncs(await listSourceSyncs(source.id))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load sync history')
    }
  }

  async function handleDelete(source: DataSource) {
    if (!window.confirm(`Disconnect ${source.name}? Connector-created documents will also be removed.`)) return
    try {
      await deleteSource(source.id)
      setSources((current) => current.filter((item) => item.id !== source.id))
      if (selected?.id === source.id) setSelected(null)
      setMessage(`${source.name} disconnected`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to disconnect source')
    }
  }

  return (
    <div className='space-y-6'>
      <Card title='Connect a knowledge source'>
        <form className='space-y-3' onSubmit={handleCreate}>
          <div className='grid gap-3 md:grid-cols-2'>
            <Input required placeholder='Connection name' value={name} onChange={(e) => setName(e.target.value)} />
            <select className='rounded-md border border-input bg-background px-3 py-2 text-sm' value={type} onChange={(e) => setType(e.target.value as ConnectorType)}>
              {connectorTypes.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>
          <textarea className='min-h-20 w-full rounded-md border border-input bg-background p-3 text-sm' aria-label='Connector configuration JSON' value={config} onChange={(e) => setConfig(e.target.value)} />
          <textarea className='min-h-20 w-full rounded-md border border-input bg-background p-3 text-sm' aria-label='Connector credentials JSON' value={credentials} onChange={(e) => setCredentials(e.target.value)} />
          <p className='text-xs text-muted-foreground'>Configuration and credentials are validated by the backend. Credentials are encrypted and never returned.</p>
          <Button type='submit' disabled={saving}>{saving ? 'Creating...' : 'Create source'}</Button>
        </form>
      </Card>

      <Card title='Connected sources'>
        {loading && <p className='text-muted-foreground'>Loading sources...</p>}
        {!loading && sources.length === 0 && <p className='text-muted-foreground'>No sources connected yet.</p>}
        <div className='space-y-3'>
          {sources.map((source) => (
            <div key={source.id} className='rounded-md border border-border p-4'>
              <div className='flex flex-wrap items-start justify-between gap-3'>
                <button className='text-left' onClick={() => void handleSelect(source)}>
                  <p className='font-medium'>{source.name}</p>
                  <p className='text-sm text-muted-foreground'>{source.type} · {source.status}</p>
                  <p className='text-xs text-muted-foreground'>{source.last_synced_at ? `Last sync ${new Date(source.last_synced_at).toLocaleString()}` : 'Never synchronized'}</p>
                </button>
                <div className='flex gap-2'>
                  <Button size='sm' variant='outline' onClick={() => void handleTest(source)}>Test</Button>
                  <Button size='sm' onClick={() => void handleSync(source)} disabled={source.status === 'disabled'}>Sync</Button>
                  <Button size='sm' variant='ghost' onClick={() => void handleDelete(source)}>Disconnect</Button>
                </div>
              </div>
              {source.last_error && <p className='mt-2 text-sm text-red-600'>{source.last_error}</p>}
              {selected?.id === source.id && (
                <div className='mt-4 border-t border-border pt-3'>
                  <p className='text-sm font-medium'>Recent synchronization</p>
                  {syncs.length === 0 ? <p className='text-sm text-muted-foreground'>No sync runs recorded.</p> : syncs.map((job) => (
                    <p key={job.id} className='text-sm text-muted-foreground'>{job.status} · {job.fetched} fetched · {job.ingested} ingested · {job.failed} failed</p>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {message && <p className='text-sm text-green-700'>{message}</p>}
      {error && <p className='text-sm text-red-600'>{error}</p>}
    </div>
  )
}
