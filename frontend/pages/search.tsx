import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ArrowRight, BookOpen, Filter, Search, Sparkles, TextSearch, Waypoints } from 'lucide-react'
import { SearchResponse, searchKnowledge } from '@/src/api'
import { Badge, EmptyState, PageHeader, cn } from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'

const MODES: Array<{ value: SearchResponse['mode']; label: string; description: string; icon: React.ReactNode }> = [
  { value: 'hybrid', label: 'Hybrid', description: 'Dense + lexical with reciprocal rank fusion', icon: <Waypoints /> },
  { value: 'semantic', label: 'Semantic', description: 'Embedding similarity for meaning-level recall', icon: <Sparkles /> },
  { value: 'lexical', label: 'Lexical', description: 'Exact term matching for names and identifiers', icon: <TextSearch /> },
]

function highlight(text: string, query: string): React.ReactNode {
  const terms = query.split(/\s+/).map((term) => term.trim()).filter((term) => term.length > 2).slice(0, 5)
  if (!terms.length) return text
  const pattern = new RegExp(`(${terms.map((term) => term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'ig')
  const lowerTerms = new Set(terms.map((term) => term.toLowerCase()))
  return text.split(pattern).map((part, index) =>
    lowerTerms.has(part.toLowerCase()) ? (
      <mark key={index} style={{ background: 'rgba(34,211,238,.18)', color: 'inherit', borderRadius: 3, padding: '0 2px' }}>{part}</mark>
    ) : (
      <React.Fragment key={index}>{part}</React.Fragment>
    ),
  )
}

export default function KnowledgeSearch() {
  const [params, setParams] = useSearchParams()
  const initial = params.get('q') ?? ''
  const [query, setQuery] = useState(initial)
  const [mode, setMode] = useState<SearchResponse['mode']>('hybrid')
  const [topK, setTopK] = useState(8)
  const [result, setResult] = useState<SearchResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [searched, setSearched] = useState('')
  const [history, setHistory] = useState<string[]>(() => {
    try {
      return JSON.parse(sessionStorage.getItem('nexus_search_history') ?? '[]') as string[]
    } catch {
      return []
    }
  })

  const runSearch = useCallback(async (value: string, nextMode = mode, nextTopK = topK) => {
    const trimmed = value.trim()
    if (!trimmed) return
    setLoading(true)
    setError(null)
    try {
      const response = await searchKnowledge(trimmed, nextMode, nextTopK)
      setResult(response)
      setSearched(trimmed)
      setHistory((current) => {
        const next = [trimmed, ...current.filter((item) => item !== trimmed)].slice(0, 6)
        sessionStorage.setItem('nexus_search_history', JSON.stringify(next))
        return next
      })
      setParams({ q: trimmed }, { replace: true })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Search failed')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }, [mode, setParams, topK])

  useEffect(() => {
    if (initial && initial !== searched) {
      setQuery(initial)
      void runSearch(initial, pathModeFromParams(params), topK)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const modeMeta = useMemo(() => MODES.find((item) => item.value === (result?.mode ?? mode)) ?? MODES[0], [mode, result])

  function submit(event: React.FormEvent) {
    event.preventDefault()
    void runSearch(query)
  }

  function pathModeFromParams(values: URLSearchParams): SearchResponse['mode'] {
    const value = values.get('mode')
    return value === 'semantic' || value === 'lexical' ? value : 'hybrid'
  }

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Federated retrieval"
        title="Knowledge search"
        description="Search every permitted source through the same hybrid retrieval engine used by chat, specialists and the supervisor."
        actions={<Badge tone="success" dot>permission filtered</Badge>}
      />

      <section className="nx-hero" style={{ padding: 'clamp(20px, 3vw, 32px)' }}>
        <div style={{ position: 'relative', zIndex: 2 }}>
          <form onSubmit={submit} className="nx-stack" style={{ gap: 12 }}>
            <div style={{ position: 'relative' }}>
              <Search size={19} style={{ position: 'absolute', left: 17, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Ask a question or search for a phrase, identifier or name…"
                style={{ height: 56, borderRadius: 16, paddingLeft: 46, paddingRight: 120, fontSize: 14, background: 'var(--nx-surface-raised)' }}
                autoFocus
              />
              <Button type="submit" loading={loading} style={{ position: 'absolute', right: 8, top: 8, height: 40 }}>
                Search <ArrowRight size={14} />
              </Button>
            </div>

            <div className="nx-row nx-row--between">
              <div className="nx-tabs">
                {MODES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={cn('nx-tab', mode === item.value && 'is-active')}
                    onClick={() => { setMode(item.value); if (query.trim()) void runSearch(query, item.value, topK) }}
                  >
                    {item.icon}{item.label}
                  </button>
                ))}
              </div>
              <div className="nx-row" style={{ gap: 7 }}>
                <span className="nx-xs nx-muted">Results</span>
                <Select value={topK} onChange={(event) => setTopK(Number(event.target.value))} style={{ width: 82, minHeight: 34 }}>
                  {[5, 8, 10, 15, 20].map((value) => <option key={value} value={value}>{value}</option>)}
                </Select>
              </div>
            </div>
            <p className="nx-xs nx-muted" style={{ margin: 0 }}>{modeMeta.description}</p>
          </form>
        </div>
      </section>

      {error && <div className="nx-error">{error}</div>}

      {history.length > 0 && !result && (
        <Card title="Recent searches" subtitle="Stored for this browser session only">
          <div className="nx-row" style={{ gap: 7 }}>
            {history.map((item) => (
              <button key={item} type="button" className="nx-badge" style={{ cursor: 'pointer', textTransform: 'none', letterSpacing: 0 }} onClick={() => { setQuery(item); void runSearch(item) }}>
                {item}
              </button>
            ))}
          </div>
        </Card>
      )}

      {loading && (
        <div className="nx-stack">
          {[1, 2, 3].map((key) => <div key={key} className="nx-skeleton" style={{ height: 110 }} />)}
        </div>
      )}

      {!loading && !result && history.length === 0 && (
        <Card>
          <EmptyState
            icon={<BookOpen />}
            title="Search your organization's knowledge"
            description="Try a natural-language question, a project name, or an exact identifier. Hybrid mode combines meaning and exact terms."
            action={
              <div className="nx-row" style={{ gap: 7, justifyContent: 'center' }}>
                {['What is our retention policy?', 'Latest architecture decisions', 'Onboarding checklist'].map((sample) => (
                  <button key={sample} type="button" className="nx-badge" style={{ cursor: 'pointer', textTransform: 'none', letterSpacing: 0 }} onClick={() => { setQuery(sample); void runSearch(sample) }}>
                    {sample}
                  </button>
                ))}
              </div>
            }
          />
        </Card>
      )}

      {!loading && result && (
        <div className="nx-stack">
          <div className="nx-row nx-row--between">
            <p className="nx-small nx-muted" style={{ margin: 0 }}>
              <strong style={{ color: 'var(--nx-text)' }}>{result.total}</strong> result{result.total === 1 ? '' : 's'} for “{searched}” · {modeMeta.label}
            </p>
            <div className="nx-row" style={{ gap: 6 }}>
              <Badge tone="info"><Filter size={10} /> permitted evidence</Badge>
            </div>
          </div>

          {result.hits.length === 0 ? (
            <Card>
              <EmptyState
                icon={<Search />}
                title="No permitted evidence matched"
                description="Try broader terms, a different retrieval mode, or ingest additional sources. Access filters are applied before results are returned."
              />
            </Card>
          ) : (
            result.hits.map((hit, index) => (
              <article key={hit.chunk_id} className="nx-card nx-card--hover" style={{ padding: 20 }}>
                <div className="nx-row nx-row--between" style={{ alignItems: 'flex-start' }}>
                  <div className="nx-row" style={{ alignItems: 'flex-start', gap: 12 }}>
                    <span className="nx-avatar" style={{ borderRadius: 12 }}>{index + 1}</span>
                    <div style={{ minWidth: 0 }}>
                      <h3 style={{ margin: 0, fontSize: 13.5, fontWeight: 750 }}>{hit.document_filename}</h3>
                      <p className="nx-xs nx-muted" style={{ margin: '4px 0 0' }}>
                        chunk {hit.chunk_index + 1} · {hit.mode} · <span className="nx-mono">{hit.document_id.slice(0, 8)}…</span>
                      </p>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right', minWidth: 90 }}>
                    <p className="nx-xs nx-muted" style={{ margin: 0 }}>score</p>
                    <p className="nx-mono" style={{ margin: '2px 0 0', fontSize: 12, fontWeight: 700 }}>{hit.score.toFixed(4)}</p>
                    <div className="nx-score" style={{ marginTop: 5, marginLeft: 'auto' }}>
                      <span style={{ width: `${Math.max(4, Math.min(100, hit.score * 100))}%` }} />
                    </div>
                  </div>
                </div>

                <p className="nx-small nx-soft" style={{ margin: '14px 0 0', lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>
                  {highlight(hit.text, searched)}
                </p>

                {hit.provenance.length > 0 && (
                  <div className="nx-row" style={{ marginTop: 12, gap: 6 }}>
                    {hit.provenance.map((item, provenanceIndex) => (
                      <span key={provenanceIndex} className="nx-badge">
                        {String(item.kind ?? 'source')}{item.page_number ? ` · p.${item.page_number}` : ''}{item.row ? ` · row ${item.row}` : ''}{item.sheet ? ` · ${item.sheet}` : ''}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            ))
          )}
        </div>
      )}
    </div>
  )
}
