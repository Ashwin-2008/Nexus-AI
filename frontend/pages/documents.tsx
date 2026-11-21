import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Eye,
  FileArchive,
  FileText,
  FileType2,
  GitCompare,
  Layers,
  RefreshCw,
  RotateCcw,
  Search,
  Trash2,
  Upload,
  UploadCloud,
} from 'lucide-react'
import {
  Document,
  DocumentComparison,
  ExtractedDocument,
  compareDocuments,
  extractDocument,
  listDocuments,
  ragDeleteDocument,
  ragDeleteDocumentIndex,
  ragReindexDocument,
  retryDocument,
  uploadDocument,
} from '@/src/api'
import { EmptyState, Modal, PageHeader, StatCard, StatusBadge, cn, formatDate, formatNumber, timeAgo } from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Select } from '@/components/ui/input'

const ACCEPTED = '.pdf,.docx,.txt,.md,.csv,.xlsx,.pptx,.html,.htm,.json,.eml'
const FILTERS = ['all', 'completed', 'processing', 'pending', 'failed'] as const
type Filter = (typeof FILTERS)[number]

function iconFor(contentType: string, filename: string) {
  const lower = filename.toLowerCase()
  if (/pdf/.test(contentType) || lower.endsWith('.pdf')) return <FileText />
  if (/sheet|excel|csv/.test(contentType) || /\.(csv|xlsx)$/.test(lower)) return <FileArchive />
  if (/presentation|powerpoint/.test(contentType) || lower.endsWith('.pptx')) return <Layers />
  return <FileType2 />
}

function prettySize(bytes: number): string {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function DocumentExplorer() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<Filter>('all')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [selected, setSelected] = useState<Document | null>(null)
  const [preview, setPreview] = useState<ExtractedDocument | null>(null)
  const [compareMode, setCompareMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [comparison, setComparison] = useState<DocumentComparison | null>(null)
  const [comparing, setComparing] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const refresh = useCallback(async () => {
    try {
      setDocuments(await listDocuments())
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load documents')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const hasActive = documents.some((document) => ['pending', 'processing'].includes(document.status))
  useEffect(() => {
    if (!hasActive) return
    const timer = window.setInterval(() => void refresh(), 5000)
    return () => window.clearInterval(timer)
  }, [hasActive, refresh])

  const counts = useMemo(
    () => ({
      total: documents.length,
      completed: documents.filter((document) => document.status === 'completed').length,
      processing: documents.filter((document) => ['pending', 'processing'].includes(document.status)).length,
      failed: documents.filter((document) => document.status === 'failed').length,
    }),
    [documents],
  )

  const visible = useMemo(
    () =>
      documents.filter((document) => {
        const matchesFilter = filter === 'all' || document.status === filter
        const value = search.trim().toLowerCase()
        const matchesSearch = !value || document.filename.toLowerCase().includes(value) || document.content_type.toLowerCase().includes(value)
        return matchesFilter && matchesSearch
      }),
    [documents, filter, search],
  )

  async function upload(file: File) {
    setUploading(true)
    setError(null)
    setMessage(null)
    try {
      const uploaded = await uploadDocument(file)
      setDocuments((current) => [uploaded, ...current])
      setMessage(`${file.name} uploaded. Ingestion is running in the background.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  async function onPick(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (file) await upload(file)
  }

  async function onDrop(event: React.DragEvent) {
    event.preventDefault()
    setDragging(false)
    const file = event.dataTransfer.files?.[0]
    if (file) await upload(file)
  }

  async function retry(document: Document) {
    setBusyId(document.id)
    try {
      const updated = await retryDocument(document.id)
      setDocuments((current) => current.map((item) => item.id === document.id ? updated : item))
      setMessage(`${document.filename} queued for another ingestion attempt.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Retry failed')
    } finally {
      setBusyId(null)
    }
  }

  async function reindex(document: Document) {
    setBusyId(document.id)
    try {
      await ragReindexDocument(document.id)
      setMessage(`${document.filename} reindexing started.`)
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Reindex failed')
    } finally {
      setBusyId(null)
    }
  }

  async function removeIndex(document: Document) {
    if (!window.confirm(`Delete the vector and lexical index for ${document.filename}? The document record is kept.`)) return
    setBusyId(document.id)
    try {
      const result = await ragDeleteDocumentIndex(document.id)
      setMessage(`Removed ${formatNumber(Number(result.deleted_chunks ?? 0))} chunks from the index.`)
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to delete index')
    } finally {
      setBusyId(null)
    }
  }

  async function removeDocument(document: Document) {
    if (!window.confirm(`Delete ${document.filename} permanently? This removes the record, chunks and index entries.`)) return
    setBusyId(document.id)
    try {
      await ragDeleteDocument(document.id)
      setDocuments((current) => current.filter((item) => item.id !== document.id))
      setSelected(null)
      setMessage(`${document.filename} deleted.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to delete document')
    } finally {
      setBusyId(null)
    }
  }

  async function openPreview(document: Document) {
    setBusyId(document.id)
    setError(null)
    try {
      setPreview(await extractDocument(document.id))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to extract document text')
    } finally {
      setBusyId(null)
    }
  }

  function toggleCompare(document: Document) {
    setSelectedIds((current) => current.includes(document.id)
      ? current.filter((id) => id !== document.id)
      : [...current, document.id].slice(0, 20))
  }

  async function runCompare() {
    if (selectedIds.length < 2) return
    setComparing(true)
    setError(null)
    try {
      setComparison(await compareDocuments(selectedIds))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to compare documents')
    } finally {
      setComparing(false)
    }
  }

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Knowledge library"
        title="Documents"
        description="Upload, inspect and repair the documents feeding your retrieval index. Ingestion uses the shared RAG pipeline."
        actions={
          <>
            <Button variant={compareMode ? 'outline' : 'ghost'} onClick={() => { setCompareMode((current) => !current); setSelectedIds([]); setComparison(null) }}>
              <GitCompare size={14} /> {compareMode ? 'Exit compare' : 'Compare'}
            </Button>
            {compareMode && (
              <Button onClick={() => void runCompare()} loading={comparing} disabled={selectedIds.length < 2}>
                Compare {selectedIds.length || ''}
              </Button>
            )}
            <Button variant="secondary" onClick={() => void refresh()} loading={loading}><RefreshCw size={14} /> Refresh</Button>
            <Button onClick={() => fileInput.current?.click()} loading={uploading}><Upload size={14} /> Upload document</Button>
          </>
        }
      />

      <input ref={fileInput} type="file" hidden accept={ACCEPTED} onChange={onPick} />

      <section className="nx-grid nx-grid--4">
        <StatCard icon={<FileText />} label="Documents" value={counts.total} meta="Organization library" />
        <StatCard icon={<CheckCircle2 />} label="Indexed" value={counts.completed} meta="Ready for retrieval" accent="green" />
        <StatCard icon={<Clock3 />} label="In progress" value={counts.processing} meta="Queued or processing" accent="violet" />
        <StatCard icon={<AlertTriangle />} label="Failed" value={counts.failed} meta="Needs another attempt" accent="pink" />
      </section>

      <div
        className={cn('nx-drop', dragging && 'is-dragging')}
        onDragOver={(event) => { event.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => void onDrop(event)}
        role="button"
        tabIndex={0}
        onClick={() => fileInput.current?.click()}
        onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') fileInput.current?.click() }}
      >
        <UploadCloud />
        <p style={{ margin: 0, fontSize: 13, fontWeight: 700 }}>{uploading ? 'Uploading…' : 'Drop a document here, or click to browse'}</p>
        <p className="nx-xs nx-muted" style={{ margin: 0 }}>
          PDF, DOCX, TXT, Markdown, CSV, XLSX, PPTX, HTML, JSON and EML · one file at a time
        </p>
        <div className="nx-row" style={{ gap: 6, marginTop: 4 }}>
          {['PDF', 'DOCX', 'XLSX', 'PPTX', 'HTML', 'EML'].map((label) => <span key={label} className="nx-badge">{label}</span>)}
        </div>
      </div>

      {error && <div className="nx-error">{error}</div>}
      {message && <div className="nx-success">{message}</div>}

      <Card
        title="Library"
        subtitle={`${visible.length} of ${documents.length} documents`}
        actions={
          <div className="nx-row" style={{ gap: 8 }}>
            <div style={{ position: 'relative' }}>
              <Search size={13} style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--nx-muted)' }} />
              <Input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Filter by name or type…" style={{ width: 230, paddingLeft: 32, minHeight: 34 }} />
            </div>
            <Select value={filter} onChange={(event) => setFilter(event.target.value as Filter)} style={{ width: 145, minHeight: 34 }}>
              {FILTERS.map((value) => <option key={value} value={value}>{value === 'all' ? 'All statuses' : value}</option>)}
            </Select>
          </div>
        }
        flush
      >
        {loading ? (
          <div className="nx-stack" style={{ padding: '0 22px 22px' }}>
            <div className="nx-skeleton" style={{ height: 38 }} />
            <div className="nx-skeleton" style={{ height: 38 }} />
            <div className="nx-skeleton" style={{ height: 38 }} />
          </div>
        ) : visible.length === 0 ? (
          <EmptyState
            icon={<FileText />}
            title={documents.length ? 'No documents match this filter' : 'No documents yet'}
            description={documents.length ? 'Adjust the search text or status filter.' : 'Upload a file or connect a source to start building your knowledge base.'}
            action={!documents.length ? <Button size="sm" onClick={() => fileInput.current?.click()}><Upload size={13} /> Upload a document</Button> : undefined}
          />
        ) : (
          <div className="nx-table__wrap" style={{ border: 0, borderRadius: 0, background: 'transparent' }}>
            <table className="nx-table">
              <thead>
                <tr>
                  {compareMode && <th style={{ width: 36 }} aria-label="Select" />}
                  <th>Document</th>
                  <th>Status</th>
                  <th>Size</th>
                  <th>Updated</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((document) => (
                  <tr key={document.id}>
                    {compareMode && (
                      <td>
                        <input
                          type="checkbox"
                          checked={selectedIds.includes(document.id)}
                          onChange={() => toggleCompare(document)}
                          aria-label={`Select ${document.filename} for comparison`}
                        />
                      </td>
                    )}
                    <td>
                      <button type="button" onClick={() => setSelected(document)} style={{ display: 'flex', gap: 10, alignItems: 'center', border: 0, background: 'transparent', color: 'inherit', textAlign: 'left', padding: 0, maxWidth: 520 }}>
                        <span className="nx-list-item__icon" style={{ width: 34, height: 34 }}>{iconFor(document.content_type, document.filename)}</span>
                        <span style={{ minWidth: 0 }}>
                          <span className="nx-small" style={{ display: 'block', fontWeight: 700, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{document.filename}</span>
                          <span className="nx-xs nx-muted" style={{ display: 'block' }}>{document.content_type || 'unknown'}{document.metadata?.chunk_count ? ` · ${document.metadata.chunk_count} chunks` : ''}</span>
                        </span>
                      </button>
                    </td>
                    <td><StatusBadge status={document.status} /></td>
                    <td className="nx-nowrap">{prettySize(document.file_size)}</td>
                    <td className="nx-nowrap nx-xs nx-muted">{timeAgo(document.updated_at)}</td>
                    <td>
                      <div className="nx-row" style={{ justifyContent: 'flex-end', gap: 5 }}>
                        {document.status === 'failed' && (
                          <Button size="sm" variant="outline" onClick={() => void retry(document)} loading={busyId === document.id}><RotateCcw size={12} /> Retry</Button>
                        )}
                        <Button size="sm" variant="ghost" onClick={() => void openPreview(document)} loading={busyId === document.id}><Eye size={12} /> Preview</Button>
                        <Button size="sm" variant="ghost" onClick={() => void reindex(document)} loading={busyId === document.id}>Reindex</Button>
                        <Button size="sm" variant="ghost" onClick={() => void removeDocument(document)} loading={busyId === document.id} aria-label={`Delete ${document.filename}`} style={{ color: 'var(--nx-danger)' }}>
                          <Trash2 size={13} />
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={Boolean(selected)} onClose={() => setSelected(null)} title={selected?.filename ?? 'Document detail'}>
        {selected && (
          <div className="nx-stack" style={{ gap: 15 }}>
            <div className="nx-row nx-row--between">
              <div className="nx-row" style={{ gap: 10 }}>
                <span className="nx-stat__icon" style={{ width: 42, height: 42 }}>{iconFor(selected.content_type, selected.filename)}</span>
                <div>
                  <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>{selected.content_type || 'unknown type'}</p>
                  <p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>{prettySize(selected.file_size)} · uploaded {formatDate(selected.created_at)}</p>
                </div>
              </div>
              <StatusBadge status={selected.status} />
            </div>

            {selected.error_message && <div className="nx-error">{selected.error_message}</div>}

            <div className="nx-grid nx-grid--2" style={{ gap: 10 }}>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><Clock3 /></span>
                <div className="nx-list-item__body">
                  <p className="nx-list-item__title">Last update</p>
                  <p className="nx-list-item__sub">{formatDate(selected.updated_at)}</p>
                </div>
              </div>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><RotateCcw /></span>
                <div className="nx-list-item__body">
                  <p className="nx-list-item__title">Retry count</p>
                  <p className="nx-list-item__sub">{selected.retry_count ?? 0}</p>
                </div>
              </div>
            </div>

            {selected.latest_job && (
              <div>
                <p className="nx-label" style={{ marginBottom: 8 }}>Latest ingestion job</p>
                <div className="nx-table__wrap">
                  <table className="nx-table">
                    <tbody>
                      <tr><td className="nx-muted">Status</td><td><StatusBadge status={selected.latest_job.status} /></td></tr>
                      <tr><td className="nx-muted">Attempt</td><td>{selected.latest_job.attempt} / {selected.latest_job.max_attempts}</td></tr>
                      <tr><td className="nx-muted">Started</td><td className="nx-xs">{formatDate(selected.latest_job.started_at)}</td></tr>
                      <tr><td className="nx-muted">Finished</td><td className="nx-xs">{formatDate(selected.latest_job.finished_at)}</td></tr>
                      {selected.latest_job.error_message && <tr><td className="nx-muted">Error</td><td style={{ color: 'var(--nx-danger)' }}>{selected.latest_job.error_message}</td></tr>}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <details className="nx-details">
              <summary>Metadata</summary>
              <div><pre className="nx-code">{JSON.stringify(selected.metadata ?? {}, null, 2)}</pre></div>
            </details>

            <div className="nx-row nx-row--between">
              <Button variant="ghost" onClick={() => void removeDocument(selected)} style={{ color: 'var(--nx-danger)' }}><Trash2 size={13} /> Delete</Button>
              <div className="nx-row" style={{ gap: 8 }}>
                <Button variant="outline" onClick={() => void removeIndex(selected)} loading={busyId === selected.id}>Delete index</Button>
                <Button onClick={() => void reindex(selected)} loading={busyId === selected.id}><RefreshCw size={13} /> Reindex</Button>
              </div>
            </div>
          </div>
        )}
      </Modal>

      <Modal open={Boolean(preview)} onClose={() => setPreview(null)} title={preview ? `${preview.filename} · extracted text` : 'Document preview'}>
        {preview && (
          <div className="nx-stack" style={{ gap: 14 }}>
            <div className="nx-row nx-row--between">
              <p className="nx-xs nx-muted" style={{ margin: 0 }}>
                {formatNumber(preview.text.length)} extracted characters · {preview.spans.length} source spans
              </p>
            </div>

            {preview.warnings.length > 0 && <div className="nx-error">{preview.warnings.join(' · ')}</div>}

            <div className="nx-grid nx-grid--3">
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><FileText /></span>
                <div className="nx-list-item__body"><p className="nx-list-item__title">Dates</p><p className="nx-list-item__sub">{preview.dates.length}</p></div>
              </div>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><Layers /></span>
                <div className="nx-list-item__body"><p className="nx-list-item__title">Entities</p><p className="nx-list-item__sub">{preview.entities.length}</p></div>
              </div>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><CheckCircle2 /></span>
                <div className="nx-list-item__body"><p className="nx-list-item__title">Obligations</p><p className="nx-list-item__sub">{preview.obligations.length}</p></div>
              </div>
            </div>

            <details className="nx-details" open>
              <summary>Extracted document text</summary>
              <div>
                <pre className="nx-code" style={{ maxHeight: 360, whiteSpace: 'pre-wrap', overflow: 'auto' }}>{preview.text || 'No text was extracted from this document.'}</pre>
              </div>
            </details>

            {preview.entities.length > 0 && (
              <div>
                <p className="nx-label" style={{ marginBottom: 8 }}>Entities</p>
                <div className="nx-row" style={{ gap: 6, flexWrap: 'wrap' }}>
                  {preview.entities.slice(0, 40).map((entity) => <span key={entity} className="nx-badge">{entity}</span>)}
                </div>
              </div>
            )}

            {preview.obligations.length > 0 && (
              <div>
                <p className="nx-label" style={{ marginBottom: 8 }}>Candidate obligations</p>
                <div className="nx-stack" style={{ gap: 6 }}>
                  {preview.obligations.slice(0, 10).map((item, index) => (
                    <p key={index} className="nx-xs nx-soft" style={{ margin: 0, lineHeight: 1.6 }}>{item}</p>
                  ))}
                </div>
              </div>
            )}

            <details className="nx-details">
              <summary>Extraction metadata</summary>
              <div><pre className="nx-code">{JSON.stringify({ metadata: preview.metadata, spans: preview.spans, dates: preview.dates }, null, 2)}</pre></div>
            </details>
          </div>
        )}
      </Modal>

      <Modal open={Boolean(comparison)} onClose={() => setComparison(null)} title="Document comparison">
        {comparison && (
          <div className="nx-stack" style={{ gap: 14 }}>
            <p className="nx-xs nx-muted" style={{ margin: 0 }}>
              Comparing {comparison.documents.length} documents. Changed lines are relative to {comparison.documents[0]?.filename}.
            </p>
            <div className="nx-row" style={{ gap: 6, flexWrap: 'wrap' }}>
              {comparison.documents.map((document) => <span key={document.document_id} className="nx-badge nx-badge--violet">{document.filename}</span>)}
            </div>
            {comparison.comparisons.map((item) => (
              <div key={item.document_id}>
                <p className="nx-label" style={{ marginBottom: 8 }}>{item.filename} · {item.changed_lines.length} changed lines</p>
                {item.changed_lines.length === 0 ? (
                  <p className="nx-xs nx-muted" style={{ margin: 0 }}>No line-level differences detected.</p>
                ) : (
                  <pre className="nx-code" style={{ maxHeight: 240, overflow: 'auto' }}>
                    {item.changed_lines.map((line, index) => (
                      <span key={index} style={{ display: 'block', color: line.startsWith('+') ? 'var(--nx-success)' : line.startsWith('-') ? 'var(--nx-danger)' : undefined }}>{line}</span>
                    ))}
                  </pre>
                )}
              </div>
            ))}
            <details className="nx-details">
              <summary>Extracted metadata for each document</summary>
              <div><pre className="nx-code">{JSON.stringify(comparison.documents, null, 2)}</pre></div>
            </details>
          </div>
        )}
      </Modal>
    </div>
  )
}
