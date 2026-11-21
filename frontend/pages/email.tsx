import React, { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ArrowRight,
  Inbox,
  Mail,
  Search,
  Send,
  ShieldAlert,
  UserRound,
} from 'lucide-react'
import {
  DataSource,
  EmailSearchResult,
  createEmailDraft,
  listSources,
  searchEmail,
} from '@/src/api'
import { Badge, EmptyState, Field, PageHeader, formatDate } from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/input'

export default function EmailIntelligence() {
  const [sources, setSources] = useState<DataSource[]>([])
  const [sourceId, setSourceId] = useState('')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<EmailSearchResult | null>(null)
  const [loadingSources, setLoadingSources] = useState(true)
  const [searching, setSearching] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  const [recipients, setRecipients] = useState('')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [draftResult, setDraftResult] = useState<{ execution_id: string; approval_id: string; status: string } | null>(null)

  useEffect(() => {
    listSources()
      .then((all) => {
        const emailSources = all.filter((source) => source.type === 'email')
        setSources(emailSources)
        setSourceId((current) => current || emailSources[0]?.id || '')
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load email sources'))
      .finally(() => setLoadingSources(false))
  }, [])

  const selected = useMemo(() => sources.find((source) => source.id === sourceId) ?? null, [sourceId, sources])

  async function handleSearch(event: React.FormEvent) {
    event.preventDefault()
    if (!sourceId) return
    setSearching(true)
    setError(null)
    setMessage(null)
    try {
      setResults(await searchEmail(sourceId, query))
    } catch (caught) {
      setResults(null)
      setError(caught instanceof Error ? caught.message : 'Email search failed')
    } finally {
      setSearching(false)
    }
  }

  async function handleDraft(event: React.FormEvent) {
    event.preventDefault()
    if (!sourceId) return
    setSending(true)
    setError(null)
    setMessage(null)
    setDraftResult(null)
    try {
      const result = await createEmailDraft(
        sourceId,
        recipients.split(',').map((value) => value.trim()).filter(Boolean),
        subject.trim(),
        body.trim(),
      )
      setDraftResult(result as { execution_id: string; approval_id: string; status: string })
      setSubject('')
      setBody('')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to create email draft')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Connected intelligence"
        title="Email"
        description="Search indexed mailboxes through the configured IMAP source and prepare outbound mail. Sending always pauses for a human approval before SMTP delivery."
        actions={
          <Link to="/app/knowledge-sources"><Button variant="secondary"><Mail size={14} /> Manage email sources</Button></Link>
        }
      />

      {error && <div className="nx-error">{error}</div>}
      {message && <div className="nx-success">{message}</div>}

      {loadingSources ? (
        <div className="nx-skeleton" style={{ height: 100 }} />
      ) : sources.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Mail />}
            title="No email source configured"
            description="Connect an IMAP mailbox in Sources. Credentials are encrypted at rest and never returned by the API."
            action={<Link to="/app/knowledge-sources"><Button size="sm">Connect an email source</Button></Link>}
          />
        </Card>
      ) : (
        <div className="nx-grid nx-grid--sidebar" style={{ alignItems: 'start' }}>
          <div className="nx-stack">
            <Card title="Search mailbox" subtitle="Live IMAP fetch filtered by your query" glow="cyan">
              <form onSubmit={handleSearch} className="nx-stack" style={{ gap: 12 }}>
                <div className="nx-grid nx-grid--3" style={{ gap: 10 }}>
                  <Field label="Email source">
                    <Select value={sourceId} onChange={(event) => { setSourceId(event.target.value); setResults(null) }}>
                      {sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
                    </Select>
                  </Field>
                  <Field label="Query">
                    <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="invoice, project alpha…" />
                  </Field>
                  <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                    <Button type="submit" loading={searching} className="nx-btn--block"><Search size={13} /> Search inbox</Button>
                  </div>
                </div>
                {selected && <p className="nx-xs nx-muted" style={{ margin: 0 }}>Last synchronized {selected.last_synced_at ? formatDate(selected.last_synced_at) : 'never'}.</p>}
              </form>
            </Card>

            <Card
              title="Messages"
              subtitle={results ? `${results.count} matching message${results.count === 1 ? '' : 's'}` : 'Search results appear here'}
              actions={results ? <Badge tone="info"><Inbox size={10} /> live fetch</Badge> : undefined}
              flush
            >
              {searching ? (
                <div style={{ padding: '0 22px 22px' }} className="nx-stack">
                  <div className="nx-skeleton" style={{ height: 54 }} />
                  <div className="nx-skeleton" style={{ height: 54 }} />
                </div>
              ) : !results ? (
                <EmptyState icon={<Search />} title="Search a mailbox" description="Run a search to inspect real messages from the configured IMAP source." />
              ) : results.messages.length === 0 ? (
                <EmptyState icon={<Inbox />} title="No matching messages" description="Try a broader query or check that the mailbox contains readable text." />
              ) : (
                <div style={{ padding: '0 22px 22px' }} className="nx-stack">
                  {results.messages.map((item) => (
                    <details key={item.external_id} className="nx-details">
                      <summary>
                        <span className="nx-row nx-row--between" style={{ gap: 10 }}>
                          <span className="nx-truncate">{item.subject || '(no subject)'}</span>
                          <span className="nx-xs nx-muted nx-nowrap">{item.metadata?.date ? String(item.metadata.date).slice(0, 16) : 'current'}</span>
                        </span>
                      </summary>
                      <div>
                        <p className="nx-xs nx-muted" style={{ margin: '0 0 8px', whiteSpace: 'pre-wrap', lineHeight: 1.65 }}>{item.body.slice(0, 4000)}</p>
                        {item.uri && <p className="nx-xs nx-mono nx-muted" style={{ margin: 0 }}>{item.uri}</p>}
                      </div>
                    </details>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <div className="nx-stack">
            <Card title="Draft outbound email" subtitle="Requires an approval request before sending" glow="violet">
              <form onSubmit={handleDraft} className="nx-stack" style={{ gap: 12 }}>
                <Field label="Recipients" hint="Comma-separated email addresses.">
                  <Input value={recipients} onChange={(event) => setRecipients(event.target.value)} placeholder="ops@example.com" required />
                </Field>
                <Field label="Subject">
                  <Input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Follow-up on Project Alpha" required />
                </Field>
                <Field label="Body">
                  <Textarea value={body} onChange={(event) => setBody(event.target.value)} placeholder="Write the message…" style={{ minHeight: 150 }} required />
                </Field>
                <Button type="submit" loading={sending}><Send size={13} /> Create approval request</Button>
              </form>
            </Card>

            {draftResult && (
              <Card title="Approval requested" subtitle="No email has been sent yet">
                <div className="nx-stack" style={{ gap: 10 }}>
                  <div className="nx-row" style={{ gap: 8 }}>
                    <Badge tone="warning" dot><ShieldAlert size={10} /> {draftResult.status.replaceAll('_', ' ')}</Badge>
                    <Badge>{draftResult.approval_id.slice(0, 8)}</Badge>
                  </div>
                  <p className="nx-xs nx-muted" style={{ margin: 0, lineHeight: 1.6 }}>
                    A second person with approval authority must approve this action in the Agent control center. SMTP delivery only happens after that decision.
                  </p>
                  <Link to="/app/agent-control-center" className="nx-btn nx-btn--outline nx-btn--sm">
                    Review approval <ArrowRight size={12} />
                  </Link>
                </div>
              </Card>
            )}

            <Card title="Connector guardrails" subtitle="What the email surface enforces">
              <div className="nx-timeline">
                <div className="nx-timeline__item">
                  <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Encrypted credentials</p>
                  <p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>IMAP and SMTP credentials are decrypted only server-side for the configured connection.</p>
                </div>
                <div className="nx-timeline__item">
                  <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Human approval</p>
                  <p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>Outbound email is a high-risk action and never auto-sends from this console.</p>
                </div>
                <div className="nx-timeline__item">
                  <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Delivery errors surface</p>
                  <p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>SMTP failures are recorded on the execution and returned as an explicit error.</p>
                </div>
              </div>
            </Card>

            <Card title="Selected source" subtitle="Connection used for this session">
              <div className="nx-list">
                <div className="nx-list-item">
                  <span className="nx-list-item__icon"><Mail /></span>
                  <div className="nx-list-item__body">
                    <p className="nx-list-item__title">{selected?.name ?? 'None selected'}</p>
                    <p className="nx-list-item__sub">{selected?.status ?? 'unknown'} · {selected?.type ?? 'email'}</p>
                  </div>
                </div>
                <div className="nx-list-item">
                  <span className="nx-list-item__icon"><UserRound /></span>
                  <div className="nx-list-item__body">
                    <p className="nx-list-item__title">Credentials</p>
                    <p className="nx-list-item__sub">Encrypted and masked in every API response</p>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
