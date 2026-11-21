import React from 'react'
import { Card, Button, Input } from '@/components/ui'
import { SearchResponse, searchKnowledge } from '@/src/api'

export default function KnowledgeSearch() {
  const [query, setQuery] = React.useState('')
  const [mode, setMode] = React.useState<SearchResponse['mode']>('hybrid')
  const [result, setResult] = React.useState<SearchResponse | null>(null)
  const [loading, setLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      setResult(await searchKnowledge(query.trim(), mode))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className='space-y-6'>
      <Card title='Knowledge search'>
        <form className='flex flex-col gap-3 md:flex-row' onSubmit={submit}>
          <Input className='flex-1' placeholder='Search permitted organizational knowledge...' value={query} onChange={(e) => setQuery(e.target.value)} />
          <select className='rounded-md border border-input bg-background px-3 py-2 text-sm' value={mode} onChange={(e) => setMode(e.target.value as SearchResponse['mode'])}>
            <option value='hybrid'>Hybrid</option>
            <option value='semantic'>Semantic</option>
            <option value='lexical'>Lexical</option>
          </select>
          <Button type='submit' disabled={loading}>{loading ? 'Searching...' : 'Search'}</Button>
        </form>
      </Card>
      {error && <p className='text-sm text-red-600'>{error}</p>}
      {result && <Card title={`${result.total} result${result.total === 1 ? '' : 's'} · ${result.mode}`}>
        <div className='space-y-4'>
          {result.hits.map((hit) => (
            <article key={hit.chunk_id} className='border-b border-border pb-4 last:border-0'>
              <div className='flex items-center justify-between gap-3'>
                <h3 className='font-medium'>{hit.document_filename}</h3>
                <span className='text-xs text-muted-foreground'>score {hit.score.toFixed(3)}</span>
              </div>
              <p className='mt-1 whitespace-pre-wrap text-sm text-muted-foreground'>{hit.text}</p>
              {hit.provenance.length > 0 && <p className='mt-2 text-xs text-muted-foreground'>{JSON.stringify(hit.provenance)}</p>}
            </article>
          ))}
          {result.hits.length === 0 && <p className='text-muted-foreground'>No permitted evidence matched this query.</p>}
        </div>
      </Card>}
    </div>
  )
}
