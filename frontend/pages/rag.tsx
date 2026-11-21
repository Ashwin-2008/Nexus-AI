import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  Braces,
  Database,
  FileSearch,
  FileStack,
  FlaskConical,
  Gauge,
  Layers,
  Play,
  RefreshCw,
  Scissors,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import {
  RagEvaluationSummary,
  RagEvidence,
  RagQueryResponse,
  RagSourceDocument,
  RagStatus,
  ragConfig,
  ragDeleteDocumentIndex,
  ragEvaluation,
  ragEvaluations,
  ragHealth,
  ragIngestText,
  ragQuery,
  ragRunEvaluation,
  ragReindexDocument,
  ragSources,
  ragStatus,
} from '@/src/api'
import { useAuth } from '@/src/auth'
import {
  Badge,
  EmptyState,
  Field,
  PageHeader,
  StatCard,
  StatusBadge,
  cn,
  formatNumber,
  timeAgo,
} from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/input'

type Tab = 'query' | 'ingest' | 'index' | 'evaluate'
type Mode = 'hybrid' | 'dense' | 'sparse'

const VERIFICATION_TONES: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'violet'> = {
  supported: 'success',
  partially_supported: 'warning',
  unsupported: 'danger',
  conflicting_evidence: 'danger',
  insufficient_evidence: 'info',
}

function EvidenceCard({ evidence, index }: { evidence: RagEvidence; index: number }) {
  return (
    <details className="nx-details">
      <summary>
        <div className="nx-row nx-row--between" style={{ gap: 8 }}>
          <span className="nx-row" style={{ gap: 8, minWidth: 0 }}>
            <span className="nx-badge nx-badge--violet">#{index + 1}</span>
            <span className="nx-truncate">{evidence.document_filename}</span>
          </span>
          <span className="nx-xs nx-muted nx-nowrap">
            {evidence.rerank_score != null ? `rerank ${evidence.rerank_score.toFixed(3)}` : `score ${evidence.score.toFixed(3)}`}
          </span>
        </div>
      </summary>
      <div>
        <p className="nx-small nx-soft" style={{ margin: '0 0 10px', lineHeight: 1.65, whiteSpace: 'pre-wrap' }}>{evidence.text}</p>
        <div className="nx-row" style={{ gap: 6 }}>
          <Badge>{evidence.mode}</Badge>
          <Badge>rank {evidence.retrieval_rank}</Badge>
          <Badge>v{evidence.document_version}</Badge>
          {evidence.section_heading && <Badge tone="info">{evidence.section_heading}</Badge>}
          {evidence.source_type && <Badge tone="violet">{evidence.source_type}</Badge>}
          {evidence.provenance?.slice(0, 2).map((item, key) => (
            <Badge key={key}>{String(item.kind ?? 'source')}{item.page_number ? ` p.${item.page_number}` : ''}{item.row ? ` row ${item.row}` : ''}</Badge>
          ))}
        </div>
      </div>
    </details>
  )
}

export default function RagConsole() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const [tab, setTab] = useState<Tab>('query')
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<Mode>('hybrid')
  const [documentId, setDocumentId] = useState('')
  const [topK, setTopK] = useState(8)
  const [rerank, setRerank] = useState(true)
  const [verify, setVerify] = useState(true)
  const [answer, setAnswer] = useState<RagQueryResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)

  const [documents, setDocuments] = useState<RagSourceDocument[]>([])
  const [status, setStatus] = useState<RagStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(true)

  const [evaluations, setEvaluations] = useState<RagEvaluationSummary[]>([])
  const [evaluationDetail, setEvaluationDetail] = useState<Record<string, unknown> | null>(null)
  const [config, setConfig] = useState<Record<string, unknown> | null>(null)
  const [health, setHealth] = useState<Record<string, unknown> | null>(null)
  const [evalName, setEvalName] = useState('inline-evaluation')
  const [evalQuery, setEvalQuery] = useState('')
  const [evalDocumentId, setEvalDocumentId] = useState('')
  const [evalMode, setEvalMode] = useState<Mode>('hybrid')
  const [evalK, setEvalK] = useState(5)
  const [evalGenerate, setEvalGenerate] = useState(false)
  const [evalRunning, setEvalRunning] = useState(false)
  const [evalResult, setEvalResult] = useState<Record<string, unknown> | null>(null)
  const [evaluationsLoading, setEvaluationsLoading] = useState(false)

  const [note, setNote] = useState('')
  const [noteName, setNoteName] = useState('note.md')
  const [noteTitle, setNoteTitle] = useState('')
  const [accessScope, setAccessScope] = useState<'organization' | 'private' | 'admin'>('organization')
  const [ingesting, setIngesting] = useState(false)

  const refresh = useCallback(async () => {
    setStatusLoading(true)
    try {
      const [sources, currentStatus] = await Promise.all([ragSources(), ragStatus()])
      setDocuments(sources.documents)
      setStatus(currentStatus)
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to load RAG status')
    } finally {
      setStatusLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    if (tab !== 'evaluate' || !isAdmin) return
    let cancelled = false
    setEvaluationsLoading(true)
    Promise.allSettled([ragEvaluations(), ragConfig(), ragHealth()]).then(([runs, configResult, healthResult]) => {
      if (cancelled) return
      if (runs.status === 'fulfilled') setEvaluations(runs.value.items)
      if (configResult.status === 'fulfilled') setConfig(configResult.value)
      if (healthResult.status === 'fulfilled') setHealth(healthResult.value)
      const failed = [runs, configResult, healthResult].find((item) => item.status === 'rejected')
      if (failed && failed.status === 'rejected') {
        setError(failed.reason instanceof Error ? failed.reason.message : 'Unable to load evaluation data')
      }
      setEvaluationsLoading(false)
    })
    return () => { cancelled = true }
  }, [tab, isAdmin])

  async function submitQuery(event: React.FormEvent) {
    event.preventDefault()
    if (!query.trim() || loading) return
    setLoading(true)
    setError(null)
    setMessage(null)
    try {
      setAnswer(await ragQuery(query.trim(), {
        mode,
        topK,
        rerank,
        verify,
        includeEvidence: true,
        documentIds: documentId ? [documentId] : [],
      }))
    } catch (caught) {
      setAnswer(null)
      setError(caught instanceof Error ? caught.message : 'RAG query failed')
    } finally {
      setLoading(false)
    }
  }

  async function runEvaluation(event: React.FormEvent) {
    event.preventDefault()
    if (!evalQuery.trim() || !evalDocumentId) {
      setError('Choose a relevant document and enter an evaluation query.')
      return
    }
    setEvalRunning(true)
    setError(null)
    setMessage(null)
    setEvalResult(null)
    try {
      const result = await ragRunEvaluation({
        name: evalName || 'inline-evaluation',
        items: [{ query: evalQuery.trim(), relevant_document_ids: [evalDocumentId] }],
        k: evalK,
        generate: evalGenerate,
      })
      setEvalResult(result)
      setMessage('Evaluation completed and persisted.')
      setEvaluations((await ragEvaluations()).items)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Evaluation failed')
    } finally {
      setEvalRunning(false)
    }
  }

  async function openEvaluation(runId: string) {
    setError(null)
    try {
      setEvaluationDetail(await ragEvaluation(runId))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load evaluation run')
    }
  }

  async function submitNote(event: React.FormEvent) {
    event.preventDefault()
    if (!note.trim()) return
    setIngesting(true)
    setError(null)
    setMessage(null)
    try {
      const result = await ragIngestText({
        content: note,
        filename: noteName || 'note.md',
        title: noteTitle || undefined,
        accessScope,
      })
      setMessage(`Queued ${result.document.filename} · job ${result.job.status} · document ${result.document.status}`)
      setNote('')
      setNoteTitle('')
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Ingestion failed')
    } finally {
      setIngesting(false)
    }
  }

  async function reindex(id: string) {
    setBusyId(id)
    setError(null)
    setMessage(null)
    try {
      await ragReindexDocument(id)
      setMessage('Re-index queued through the shared ingestion pipeline.')
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Re-index failed')
    } finally {
      setBusyId(null)
    }
  }

  async function deleteIndex(id: string) {
    if (!window.confirm('Delete this document’s vector and lexical index? The document record is kept.')) return
    setBusyId(id)
    setError(null)
    setMessage(null)
    try {
      const result = await ragDeleteDocumentIndex(id)
      setMessage(`Removed ${formatNumber(Number(result.deleted_chunks ?? 0))} chunks and ${formatNumber(Number(result.deleted_points ?? 0))} vector points.`)
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Index deletion failed')
    } finally {
      setBusyId(null)
    }
  }

  const indexInfo = useMemo(() => status?.index ?? {}, [status])
  const vectorInfo = (indexInfo.vector ?? {}) as Record<string, unknown>
  const lexicalInfo = (indexInfo.lexical ?? {}) as Record<string, unknown>
  const chunks = status?.documents.chunks ?? 0
  const outOfSync = status?.sync.out_of_sync.length ?? 0

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Grounded RAG operations"
        title="RAG console"
        description="Inspect the shared retrieval pipeline end to end: query understanding, hybrid recall, reranking, permission revalidation, context assembly, generation, citations and verification."
        actions={
          <>
            <Button variant="secondary" onClick={() => void refresh()} loading={statusLoading}><RefreshCw size={14} /> Refresh</Button>
            <Badge tone={status?.capabilities.verification ? 'success' : 'warning'} dot>verification {status?.capabilities.verification ? 'on' : 'off'}</Badge>
          </>
        }
      />

      <section className="nx-grid nx-grid--4">
        <StatCard icon={<FileStack />} label="Documents" value={formatNumber(status?.documents.total ?? 0)} meta={`${formatNumber(chunks)} indexed chunks`} />
        <StatCard icon={<Database />} label="Vector backend" value={String(vectorInfo.backend ?? '—')} meta={String(vectorInfo.status ?? 'status unknown')} accent="violet" />
        <StatCard icon={<Gauge />} label="Reranker" value={status?.capabilities.reranker ?? '—'} meta={status?.capabilities.modes?.join(' · ') ?? 'modes unknown'} accent="pink" />
        <StatCard icon={<ShieldCheck />} label="Out of sync" value={formatNumber(outOfSync)} meta={`${status?.sync.sampled_documents ?? 0} documents sampled`} accent={outOfSync ? 'pink' : 'green'} />
      </section>

      <div className="nx-tabs">
        <button type="button" className={cn('nx-tab', tab === 'query' && 'is-active')} onClick={() => setTab('query')}><Sparkles /> Query</button>
        <button type="button" className={cn('nx-tab', tab === 'ingest' && 'is-active')} onClick={() => setTab('ingest')}><UploadCloud /> Ingest text</button>
        <button type="button" className={cn('nx-tab', tab === 'index' && 'is-active')} onClick={() => setTab('index')}><Layers /> Index sources</button>
        {isAdmin && <button type="button" className={cn('nx-tab', tab === 'evaluate' && 'is-active')} onClick={() => setTab('evaluate')}><FlaskConical /> Evaluate</button>}
      </div>

      {error && <div className="nx-error">{error}</div>}
      {message && <div className="nx-success">{message}</div>}

      {tab === 'query' && (
        <div className="nx-grid nx-grid--sidebar" style={{ alignItems: 'start' }}>
          <div className="nx-stack">
            <Card title="Ask the pipeline" subtitle="Real retrieval + generation over permission-checked evidence" glow="cyan">
              <form onSubmit={submitQuery} className="nx-stack" style={{ gap: 13 }}>
                <div style={{ position: 'relative' }}>
                  <Search size={17} style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
                  <Input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Ask a question over permitted organizational knowledge…"
                    style={{ height: 48, paddingLeft: 42, fontSize: 13 }}
                    autoFocus
                  />
                </div>
                <div className="nx-grid nx-grid--3" style={{ gap: 10 }}>
                  <Field label="Retrieval mode">
                    <Select value={mode} onChange={(event) => setMode(event.target.value as Mode)}>
                      <option value="hybrid">Hybrid (RRF)</option>
                      <option value="dense">Dense / semantic</option>
                      <option value="sparse">Sparse / lexical</option>
                    </Select>
                  </Field>
                  <Field label="Scope">
                    <Select value={documentId} onChange={(event) => setDocumentId(event.target.value)}>
                      <option value="">All permitted documents</option>
                      {documents.map((document) => <option key={document.id} value={document.id}>{document.filename}</option>)}
                    </Select>
                  </Field>
                  <Field label="Top K">
                    <Select value={topK} onChange={(event) => setTopK(Number(event.target.value))}>
                      {[4, 8, 12, 20].map((value) => <option key={value} value={value}>{value}</option>)}
                    </Select>
                  </Field>
                </div>
                <div className="nx-row nx-row--between">
                  <div className="nx-row" style={{ gap: 14 }}>
                    <label className="nx-xs nx-muted" style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                      <input type="checkbox" checked={rerank} onChange={(event) => setRerank(event.target.checked)} /> Rerank
                    </label>
                    <label className="nx-xs nx-muted" style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}>
                      <input type="checkbox" checked={verify} onChange={(event) => setVerify(event.target.checked)} /> Verify citations
                    </label>
                  </div>
                  <Button type="submit" loading={loading}>Run query <ArrowRight size={14} /></Button>
                </div>
              </form>
            </Card>

            {loading && (
              <Card title="Pipeline running">
                <div className="nx-stack">
                  <div className="nx-skeleton" style={{ height: 18, width: '80%' }} />
                  <div className="nx-skeleton" style={{ height: 18, width: '95%' }} />
                  <div className="nx-skeleton" style={{ height: 18, width: '60%' }} />
                </div>
              </Card>
            )}

            {!loading && !answer && (
              <Card>
                <EmptyState
                  icon={<FileSearch />}
                  title="Inspect a grounded answer"
                  description="Run a query to see retrieval mode, reranker, context size, citations, evidence spans and claim-level verification."
                />
              </Card>
            )}

            {answer && (
              <Card
                title="Grounded answer"
                subtitle={`${answer.retrieval_mode} retrieval · ${answer.context_chunk_count} context chunks`}
                actions={
                  <div className="nx-row" style={{ gap: 6 }}>
                    <Badge tone={answer.answer_mode === 'llm' ? 'success' : answer.answer_mode === 'extractive' ? 'warning' : 'info'}>{answer.answer_mode}</Badge>
                    {answer.verification && <Badge tone={VERIFICATION_TONES[answer.verification.status] ?? 'info'} dot>{answer.verification.status.replaceAll('_', ' ')}</Badge>}
                  </div>
                }
              >
                <div className="nx-stack" style={{ gap: 14 }}>
                  <p className="nx-small nx-soft" style={{ margin: 0, lineHeight: 1.75, whiteSpace: 'pre-wrap' }}>{answer.answer}</p>

                  <div className="nx-row" style={{ gap: 6 }}>
                    <Badge>{answer.model}</Badge>
                    {answer.reranker && <Badge tone="violet">rerank: {answer.reranker}</Badge>}
                    {answer.degraded_from && <Badge tone="warning">degraded from {answer.degraded_from}</Badge>}
                    {answer.insufficient_evidence && <Badge tone="warning" dot>insufficient evidence</Badge>}
                    {answer.verification && <Badge tone="info">{Math.round(answer.verification.evidence_coverage * 100)}% coverage</Badge>}
                    <Badge>{answer.timings.retrieval_ms ?? 0} ms retrieval</Badge>
                    <Badge>{answer.timings.generation_ms ?? 0} ms generation</Badge>
                  </div>

                  {answer.verification?.disclaimer && <p className="nx-xs" style={{ margin: 0, color: 'var(--nx-warning)' }}>{answer.verification.disclaimer}</p>}
                  {!!answer.warnings.length && <p className="nx-xs" style={{ margin: 0, color: 'var(--nx-warning)' }}>{answer.warnings.join(' · ')}</p>}

                  {!!answer.citations.length && (
                    <div>
                      <p className="nx-label" style={{ marginBottom: 8 }}>Citations · {answer.citations.length}</p>
                      <div className="nx-stack" style={{ gap: 7 }}>
                        {answer.citations.map((citation) => (
                          <details key={`${citation.index}-${citation.chunk_id}`} className="nx-details">
                            <summary><span className="nx-badge nx-badge--info" style={{ marginRight: 7 }}>[{citation.index}]</span>{citation.document_filename}{citation.page_number ? ` · p.${citation.page_number}` : ''}</summary>
                            <div><p className="nx-xs nx-muted" style={{ margin: 0, lineHeight: 1.65 }}>{citation.text}</p></div>
                          </details>
                        ))}
                      </div>
                    </div>
                  )}

                  {answer.verification?.claims?.length ? (
                    <div>
                      <p className="nx-label" style={{ marginBottom: 8 }}>Claim verification</p>
                      <div className="nx-stack" style={{ gap: 6 }}>
                        {answer.verification.claims.map((claim, index) => (
                          <div key={`${index}-${claim.claim.slice(0, 20)}`} className="nx-list-item" style={{ alignItems: 'flex-start' }}>
                            <Badge tone={VERIFICATION_TONES[claim.status] ?? 'info'}>{claim.status.replaceAll('_', ' ')}</Badge>
                            <div className="nx-list-item__body">
                              <p className="nx-xs" style={{ margin: 0, lineHeight: 1.55 }}>{claim.claim}</p>
                              <p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>{Math.round(claim.support_score * 100)}% support{claim.citation_indices.length ? ` · citations ${claim.citation_indices.join(', ')}` : ''}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  <p className="nx-xs nx-muted nx-mono" style={{ margin: 0 }}>trace {answer.trace_id}</p>
                </div>
              </Card>
            )}
          </div>

          <div className="nx-stack">
            <Card title="Evidence set" subtitle={answer ? `${answer.evidence.length} retrieved chunks` : 'Retrieved evidence appears here'}>
              {answer && answer.evidence.length > 0 ? (
                <div className="nx-stack" style={{ gap: 7 }}>
                  {answer.evidence.map((evidence, index) => <EvidenceCard key={`${evidence.chunk_id}-${index}`} evidence={evidence} index={index} />)}
                </div>
              ) : (
                <EmptyState icon={<Braces />} title="No evidence to inspect" description="Run a query to see the reranked evidence passed to the model." />
              )}
            </Card>

            <Card title="Pipeline capabilities" subtitle="Configured, not simulated">
              <div className="nx-stack" style={{ gap: 9 }}>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Modes</span><span className="nx-xs">{status?.capabilities.modes?.join(', ') ?? '—'}</span></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Reranker</span><Badge tone="violet">{status?.capabilities.reranker ?? '—'}</Badge></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Verification</span><Badge tone={status?.capabilities.verification ? 'success' : 'warning'}>{status?.capabilities.verification ? 'enabled' : 'disabled'}</Badge></div>
                <div className="nx-divider" style={{ margin: '4px 0' }} />
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Lexical chunks</span><span className="nx-xs">{formatNumber(Number(lexicalInfo.chunks ?? 0))}</span></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Embedded chunks</span><span className="nx-xs">{formatNumber(Number(lexicalInfo.embedded_chunks ?? 0))}</span></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Collection</span><span className="nx-xs nx-mono">{String(indexInfo.collection ?? '—')}</span></div>
              </div>
            </Card>
          </div>
        </div>
      )}

      {tab === 'ingest' && (
        <div className="nx-grid nx-grid--sidebar" style={{ alignItems: 'start' }}>
          <Card title="Ingest text" subtitle="Validation → parsing → chunking → embeddings → vector + lexical index" glow="violet">
            <form onSubmit={submitNote} className="nx-stack" style={{ gap: 14 }}>
              <div className="nx-grid nx-grid--2" style={{ gap: 10 }}>
                <Field label="Filename">
                  <Input value={noteName} onChange={(event) => setNoteName(event.target.value)} placeholder="note.md" />
                </Field>
                <Field label="Title" hint="Optional human-readable title.">
                  <Input value={noteTitle} onChange={(event) => setNoteTitle(event.target.value)} placeholder="Quarterly policy note" />
                </Field>
              </div>
              <Field label="Access scope" hint="Enforced before retrieval and again before generation.">
                <Select value={accessScope} onChange={(event) => setAccessScope(event.target.value as typeof accessScope)}>
                  <option value="organization">Organization — all permitted members</option>
                  <option value="private">Private — uploader only</option>
                  <option value="admin">Admin — administrators only</option>
                </Select>
              </Field>
              <Field label="Content">
                <Textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Paste text or Markdown to index…" style={{ minHeight: 220 }} required />
              </Field>
              <div className="nx-row nx-row--between">
                <span className="nx-xs nx-muted">Same pipeline as uploads and connectors.</span>
                <Button type="submit" loading={ingesting}><Scissors size={14} /> Ingest text</Button>
              </div>
            </form>
          </Card>
          <Card title="What happens next" subtitle="No success is reported until it is persisted">
            <div className="nx-timeline">
              <div className="nx-timeline__item"><p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Validation & hashing</p><p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>Content type, size and duplicate/version checks.</p></div>
              <div className="nx-timeline__item"><p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Chunks & embeddings</p><p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>Deterministic chunk IDs with the configured embedding provider.</p></div>
              <div className="nx-timeline__item"><p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Dual index</p><p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>Vector points and lexical rows updated together.</p></div>
              <div className="nx-timeline__item"><p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Version record</p><p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>Document version persisted for audit and revalidation.</p></div>
            </div>
          </Card>
        </div>
      )}

      {tab === 'evaluate' && isAdmin && (
        <div className="nx-grid nx-grid--sidebar" style={{ alignItems: 'start' }}>
          <div className="nx-stack">
            <Card title="Run an evaluation" subtitle="Measured retrieval and optional generation quality over a labelled query" glow="violet">
              <form onSubmit={runEvaluation} className="nx-stack" style={{ gap: 12 }}>
                <div className="nx-grid nx-grid--2" style={{ gap: 10 }}>
                  <Field label="Run name">
                    <Input value={evalName} onChange={(event) => setEvalName(event.target.value)} placeholder="inline-evaluation" />
                  </Field>
                  <Field label="Relevant document" hint="Ground truth for this query.">
                    <Select value={evalDocumentId} onChange={(event) => setEvalDocumentId(event.target.value)}>
                      <option value="">Select a document…</option>
                      {documents.map((document) => <option key={document.id} value={document.id}>{document.filename}</option>)}
                    </Select>
                  </Field>
                </div>
                <Field label="Evaluation query">
                  <Input value={evalQuery} onChange={(event) => setEvalQuery(event.target.value)} placeholder="What should retrieval find in this document?" />
                </Field>
                <div className="nx-grid nx-grid--3" style={{ gap: 10 }}>
                  <Field label="Mode">
                    <Select value={evalMode} onChange={(event) => setEvalMode(event.target.value as Mode)}>
                      <option value="hybrid">Hybrid</option>
                      <option value="dense">Dense</option>
                      <option value="sparse">Sparse</option>
                    </Select>
                  </Field>
                  <Field label="K">
                    <Select value={evalK} onChange={(event) => setEvalK(Number(event.target.value))}>
                      {[3, 5, 8, 10, 20].map((value) => <option key={value} value={value}>{value}</option>)}
                    </Select>
                  </Field>
                  <label className="nx-xs nx-muted" style={{ display: 'flex', alignItems: 'center', gap: 7, alignSelf: 'end', paddingBottom: 9, cursor: 'pointer' }}>
                    <input type="checkbox" checked={evalGenerate} onChange={(event) => setEvalGenerate(event.target.checked)} /> Score generation
                  </label>
                </div>
                <div className="nx-row nx-row--between">
                  <span className="nx-xs nx-muted">Metrics are computed by the shared retrieval pipeline; nothing is simulated.</span>
                  <Button type="submit" loading={evalRunning}><Play size={13} /> Run evaluation</Button>
                </div>
              </form>
            </Card>

            {evalResult && (
              <Card title="Evaluation result" subtitle={`${String(evalResult.name ?? 'evaluation')} · ${String(evalResult.item_count ?? 0)} item(s)`} actions={<Badge tone="success" dot>persisted</Badge>}>
                <div className="nx-grid nx-grid--3" style={{ gap: 9 }}>
                  {Object.entries((evalResult.metrics ?? {}) as Record<string, number>).map(([key, value]) => (
                    <div key={key} className="nx-list-item">
                      <div className="nx-list-item__body">
                        <p className="nx-list-item__title" style={{ textTransform: 'capitalize' }}>{key.replaceAll('_', ' ')}</p>
                        <p className="nx-list-item__sub" style={{ fontSize: 16, fontWeight: 800, color: 'var(--nx-text)' }}>{Number(value).toFixed(4)}</p>
                      </div>
                    </div>
                  ))}
                </div>
                {!!(evalResult.errors as unknown[])?.length && <div className="nx-error" style={{ marginTop: 12 }}>{(evalResult.errors as string[]).join(' · ')}</div>}
                <details className="nx-details" style={{ marginTop: 12 }}>
                  <summary>Per-item detail</summary>
                  <div><pre className="nx-code" style={{ maxHeight: 280 }}>{JSON.stringify(evalResult.items ?? [], null, 2)}</pre></div>
                </details>
              </Card>
            )}

            {evaluationDetail && (
              <Card title="Persisted run detail" subtitle={String(evaluationDetail.name ?? '')} actions={<Button size="sm" variant="ghost" onClick={() => setEvaluationDetail(null)}>Close</Button>}>
                <div className="nx-grid nx-grid--3" style={{ gap: 9 }}>
                  {Object.entries((evaluationDetail.metrics ?? {}) as Record<string, number>).map(([key, value]) => (
                    <div key={key} className="nx-list-item">
                      <div className="nx-list-item__body">
                        <p className="nx-list-item__title" style={{ textTransform: 'capitalize' }}>{key.replaceAll('_', ' ')}</p>
                        <p className="nx-list-item__sub" style={{ fontSize: 16, fontWeight: 800, color: 'var(--nx-text)' }}>{Number(value).toFixed(4)}</p>
                      </div>
                    </div>
                  ))}
                </div>
                <details className="nx-details" style={{ marginTop: 12 }}>
                  <summary>Stored report payload</summary>
                  <div><pre className="nx-code" style={{ maxHeight: 300 }}>{JSON.stringify(evaluationDetail, null, 2)}</pre></div>
                </details>
              </Card>
            )}
          </div>

          <div className="nx-stack">
            <Card title="Evaluation history" subtitle="Persisted organization runs" actions={<Badge>{evaluations.length}</Badge>}>
              {evaluationsLoading ? (
                <div className="nx-skeleton" style={{ height: 80 }} />
              ) : evaluations.length === 0 ? (
                <EmptyState icon={<FlaskConical />} title="No evaluation runs" description="Run an evaluation to establish a measured retrieval baseline." />
              ) : (
                <div className="nx-list">
                  {evaluations.map((run) => (
                    <button key={run.id} type="button" className="nx-list-item" onClick={() => void openEvaluation(run.id)} style={{ textAlign: 'left', color: 'inherit', width: '100%' }}>
                      <span className="nx-list-item__icon"><FlaskConical /></span>
                      <span className="nx-list-item__body">
                        <span className="nx-list-item__title">{run.name || run.dataset_name || 'Evaluation'}</span>
                        <span className="nx-list-item__sub">{run.item_count ?? 0} items · k={run.k ?? '—'} · {timeAgo(run.created_at)}</span>
                      </span>
                      <ArrowRight size={13} className="nx-muted" />
                    </button>
                  ))}
                </div>
              )}
            </Card>

            <Card title="Pipeline configuration" subtitle="Secret-free resolved settings" actions={<ShieldCheck size={15} className="nx-muted" />}>
              {config ? (
                <div className="nx-stack" style={{ gap: 9 }}>
                  {Object.entries(config).filter(([key]) => key !== 'warnings').map(([key, value]) => (
                    <div key={key} className="nx-row nx-row--between" style={{ alignItems: 'flex-start', gap: 10 }}>
                      <span className="nx-xs nx-muted" style={{ textTransform: 'capitalize' }}>{key.replaceAll('_', ' ')}</span>
                      <span className="nx-xs nx-mono" style={{ maxWidth: '58%', textAlign: 'right', wordBreak: 'break-word' }}>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</span>
                    </div>
                  ))}
                  {!!(config.warnings as string[] | undefined)?.length && <div className="nx-error">{(config.warnings as string[]).join(' · ')}</div>}
                </div>
              ) : (
                <p className="nx-xs nx-muted" style={{ margin: 0 }}>Configuration could not be loaded.</p>
              )}
            </Card>

            <Card title="Index health" subtitle="Live backend probe">
              {health ? (
                <div className="nx-stack" style={{ gap: 8 }}>
                  <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Status</span><StatusBadge status={String(health.status ?? 'unknown')} /></div>
                  <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Vector backend</span><span className="nx-xs">{String(((health.index as Record<string, unknown>)?.vector as Record<string, unknown>)?.backend ?? '—')}</span></div>
                  <details className="nx-details"><summary>Raw health payload</summary><div><pre className="nx-code">{JSON.stringify(health, null, 2)}</pre></div></details>
                </div>
              ) : (
                <p className="nx-xs nx-muted" style={{ margin: 0 }}>Health probe unavailable.</p>
              )}
            </Card>
          </div>
        </div>
      )}

      {tab === 'index' && (
        <Card
          title="Indexed sources"
          subtitle={`${documents.length} documents · ${formatNumber(chunks)} chunks`}
          actions={<Button size="sm" variant="outline" onClick={() => void refresh()} loading={statusLoading}><RefreshCw size={12} /> Refresh</Button>}
          flush
        >
          {statusLoading ? (
            <div style={{ padding: '0 22px 22px' }}><div className="nx-skeleton" style={{ height: 60 }} /></div>
          ) : documents.length === 0 ? (
            <EmptyState icon={<FileStack />} title="No indexed sources" description="Upload a document or ingest text to build the index." />
          ) : (
            <div className="nx-table__wrap" style={{ border: 0, borderRadius: 0, background: 'transparent' }}>
              <table className="nx-table">
                <thead><tr><th>Document</th><th>Status</th><th>Version</th><th>Chunks</th><th>Updated</th><th style={{ textAlign: 'right' }}>Actions</th></tr></thead>
                <tbody>
                  {documents.map((document) => (
                    <tr key={document.id}>
                      <td>
                        <span className="nx-row" style={{ gap: 8 }}>
                          <span className="nx-list-item__icon" style={{ width: 30, height: 30 }}><FileStack /></span>
                          <span>
                            <span className="nx-small" style={{ display: 'block', fontWeight: 700 }}>{document.filename}</span>
                            <span className="nx-xs nx-muted">{document.content_type}</span>
                          </span>
                        </span>
                      </td>
                      <td><StatusBadge status={document.status} /></td>
                      <td>v{document.version}</td>
                      <td>{formatNumber(document.chunk_count)}</td>
                      <td className="nx-xs nx-muted">{timeAgo(document.updated_at)}</td>
                      <td>
                        <div className="nx-row" style={{ justifyContent: 'flex-end', gap: 5 }}>
                          <Button size="sm" variant="outline" onClick={() => void reindex(document.id)} loading={busyId === document.id}><RefreshCw size={12} /> Re-index</Button>
                          <Button size="sm" variant="ghost" onClick={() => void deleteIndex(document.id)} loading={busyId === document.id} aria-label={`Delete index for ${document.filename}`} style={{ color: 'var(--nx-danger)' }}><Trash2 size={13} /></Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {outOfSync > 0 && (
            <div style={{ padding: '0 22px 22px' }}>
              <div className="nx-error">{outOfSync} sampled document{outOfSync === 1 ? '' : 's'} out of sync. Re-index to repair missing or stale vectors.</div>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}
