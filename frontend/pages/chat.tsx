import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  ArrowUp,
  Bot,
  CheckCircle2,
  MessageSquare,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Square,
  Trash2,
  UserRound,
  Waypoints,
} from 'lucide-react'
import {
  ChatMessage,
  Citation,
  Conversation,
  RagVerification,
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
  ragStatus,
  sendChatMessage,
} from '@/src/api'
import { useAuth } from '@/src/auth'
import { Badge, EmptyState, StatusBadge, cn, timeAgo } from '@/components/nx'
import { Button } from '@/components/ui/button'

interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  answerMode?: string
  model?: string
  insufficientEvidence?: boolean
  verification?: RagVerification | null
  warnings?: string[]
  streaming?: boolean
  latency?: number
}

const VERIFICATION_LABELS: Record<RagVerification['status'], string> = {
  supported: 'Supported by evidence',
  partially_supported: 'Partially supported',
  unsupported: 'Unsupported claims',
  conflicting_evidence: 'Conflicting evidence',
  insufficient_evidence: 'Insufficient evidence',
}

const VERIFICATION_TONES: Record<RagVerification['status'], 'success' | 'warning' | 'danger' | 'info' | 'violet'> = {
  supported: 'success',
  partially_supported: 'warning',
  unsupported: 'danger',
  conflicting_evidence: 'danger',
  insufficient_evidence: 'info',
}

const SUGGESTIONS = [
  'Summarize the latest architecture decisions.',
  'What does our onboarding process require?',
  'List open risks across the knowledge base.',
  'Compare the current and previous policy versions.',
]

function VerificationBadge({ verification }: { verification: RagVerification }) {
  const coverage = Math.round((verification.evidence_coverage ?? 0) * 100)
  return (
    <div style={{ marginTop: 10 }}>
      <Badge tone={VERIFICATION_TONES[verification.status]} dot>
        {verification.status === 'supported' ? <ShieldCheck size={10} /> : <ShieldAlert size={10} />}
        {VERIFICATION_LABELS[verification.status]} · {coverage}% coverage
      </Badge>
      {verification.status !== 'supported' && verification.disclaimer && (
        <p className="nx-xs" style={{ margin: '7px 0 0', color: 'var(--nx-warning)', lineHeight: 1.5 }}>{verification.disclaimer}</p>
      )}
      {verification.unsupported_claims.length > 0 && (
        <details className="nx-details" style={{ marginTop: 8 }}>
          <summary>{verification.unsupported_claims.length} unsupported claim{verification.unsupported_claims.length === 1 ? '' : 's'}</summary>
          <div>
            <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--nx-muted)', fontSize: 10.5, lineHeight: 1.6 }}>
              {verification.unsupported_claims.slice(0, 5).map((claim, index) => <li key={index}>{claim}</li>)}
            </ul>
          </div>
        </details>
      )}
      {verification.conflicting_claims.length > 0 && (
        <details className="nx-details" style={{ marginTop: 6 }}>
          <summary>{verification.conflicting_claims.length} conflicting claim{verification.conflicting_claims.length === 1 ? '' : 's'}</summary>
          <div>
            <ul style={{ margin: 0, paddingLeft: 16, color: 'var(--nx-muted)', fontSize: 10.5, lineHeight: 1.6 }}>
              {verification.conflicting_claims.slice(0, 5).map((claim, index) => <li key={index}>{claim}</li>)}
            </ul>
          </div>
        </details>
      )}
    </div>
  )
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null
  return (
    <div className="nx-citations">
      <p className="nx-xs nx-muted" style={{ margin: '0 0 2px', fontWeight: 700 }}>Sources · {citations.length}</p>
      {citations.map((citation) => {
        const page = citation.page_number ?? citation.provenance?.find((item) => item.kind === 'page' && item.number)?.number
        return (
          <details key={`${citation.index}-${citation.chunk_id}`} className="nx-details">
            <summary>
              <span className="nx-badge nx-badge--info" style={{ marginRight: 7 }}>[{citation.index}]</span>
              {citation.document_filename}
              {page ? ` · p.${page}` : ''}
              {citation.section_heading ? ` · ${citation.section_heading}` : ''}
            </summary>
            <div>
              <p className="nx-xs nx-muted" style={{ margin: '0 0 8px', lineHeight: 1.65 }}>{citation.text}</p>
              <div className="nx-row" style={{ gap: 6 }}>
                {citation.source_type && <Badge tone="violet">{citation.source_type}</Badge>}
                <Badge>score {citation.score.toFixed(3)}</Badge>
                {citation.provenance?.slice(0, 3).map((item, index) => (
                  <Badge key={index}>
                    {String(item.kind)}{item.row ? ` row ${item.row}` : ''}{item.sheet ? ` ${item.sheet}` : ''}
                  </Badge>
                ))}
              </div>
            </div>
          </details>
        )
      })}
    </div>
  )
}

function MessageBubble({ message, userInitials }: { message: DisplayMessage; userInitials: string }) {
  const isUser = message.role === 'user'
  return (
    <div className={cn('nx-msg', isUser ? 'nx-msg--user' : 'nx-msg--assistant')}>
      <div className="nx-msg__avatar">{isUser ? userInitials : <Sparkles size={13} />}</div>
      <div className="nx-msg__bubble">
        <p>{message.content || (message.streaming ? '' : 'No answer text returned.')}</p>
        {message.streaming && (
          <span
            style={{ display: 'inline-block', width: 7, height: 13, marginLeft: 3, verticalAlign: 'text-bottom', background: 'var(--nx-accent)', borderRadius: 2, animation: 'nx-pulse-glow 1s ease-in-out infinite' }}
            aria-label="Generating"
          />
        )}

        {!isUser && !message.streaming && (
          <>
            {message.insufficientEvidence && (
              <p className="nx-xs" style={{ margin: '10px 0 0', color: 'var(--nx-warning)' }}>
                No sufficiently relevant permitted evidence was found for this question.
              </p>
            )}

            <div className="nx-msg__meta">
              {message.answerMode && (
                <Badge tone={message.answerMode === 'llm' ? 'success' : message.answerMode === 'extractive' ? 'warning' : 'info'}>
                  {message.answerMode === 'llm' ? 'Grounded generation' : message.answerMode === 'extractive' ? 'Extractive answer' : 'No evidence'}
                </Badge>
              )}
              {message.model && <Badge>{message.model}</Badge>}
              {typeof message.latency === 'number' && <Badge>{Math.round(message.latency)} ms</Badge>}
              {message.citations.length > 0 && <Badge tone="info">{message.citations.length} citation{message.citations.length === 1 ? '' : 's'}</Badge>}
            </div>

            {message.verification && <VerificationBadge verification={message.verification} />}

            {!!message.warnings?.length && (
              <p className="nx-xs" style={{ margin: '8px 0 0', color: 'var(--nx-warning)' }}>{message.warnings.join(' · ')}</p>
            )}

            <CitationList citations={message.citations} />
          </>
        )}
      </div>
    </div>
  )
}

export default function ChatWorkspace() {
  const { user } = useAuth()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [loadingList, setLoadingList] = useState(true)
  const [loadingMessages, setLoadingMessages] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [contextCount, setContextCount] = useState<number | null>(null)
  const [retrievalMode, setRetrievalMode] = useState('hybrid')
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const userInitials = (user?.full_name || user?.email || 'U').slice(0, 2).toUpperCase()
  const activeConversation = useMemo(() => conversations.find((item) => item.id === activeId), [activeId, conversations])

  useEffect(() => {
    ragStatus()
      .then((status) => setRetrievalMode(status.capabilities.default_mode || status.capabilities.modes?.[0] || 'hybrid'))
      .catch(() => undefined)
  }, [])

  useEffect(() => {
    listConversations()
      .then((list) => {
        setConversations(list)
        if (list.length) setActiveId((current) => current ?? list[0].id)
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Failed to load conversations'))
      .finally(() => setLoadingList(false))
  }, [])

  useEffect(() => {
    if (!activeId) {
      setMessages([])
      return
    }
    let cancelled = false
    setLoadingMessages(true)
    setContextCount(null)
    listMessages(activeId)
      .then((history) => {
        if (cancelled) return
        setMessages(history.map((message: ChatMessage) => ({
          id: message.id,
          role: message.role,
          content: message.content,
          citations: message.citations ?? [],
          answerMode: message.meta?.answer_mode,
          model: message.meta?.model,
          insufficientEvidence: message.meta?.insufficient_evidence,
          verification: message.meta?.verification ?? null,
          warnings: message.meta?.warnings ?? [],
          latency: message.meta?.retrieval_latency_ms && message.meta?.generation_latency_ms
            ? message.meta.retrieval_latency_ms + message.meta.generation_latency_ms
            : undefined,
        })))
      })
      .catch((caught) => {
        if (!cancelled) setError(caught instanceof Error ? caught.message : 'Failed to load messages')
      })
      .finally(() => {
        if (!cancelled) setLoadingMessages(false)
      })
    return () => {
      cancelled = true
    }
  }, [activeId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleNewConversation() {
    try {
      const conversation = await createConversation()
      setConversations((current) => [conversation, ...current])
      setActiveId(conversation.id)
      setMessages([])
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to create conversation')
    }
  }

  async function handleDeleteConversation(id: string) {
    if (!window.confirm('Delete this conversation and its messages?')) return
    try {
      await deleteConversation(id)
      setConversations((current) => current.filter((conversation) => conversation.id !== id))
      if (activeId === id) {
        setActiveId(null)
        setMessages([])
      }
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to delete conversation')
    }
  }

  function stop() {
    abortRef.current?.abort()
    abortRef.current = null
    setSending(false)
    setMessages((current) => current.map((message) => message.streaming ? { ...message, streaming: false } : message))
  }

  async function handleSend(event?: React.FormEvent, preset?: string) {
    event?.preventDefault()
    const content = (preset ?? input).trim()
    if (!content || sending) return
    let conversationId = activeId
    try {
      if (!conversationId) {
        const conversation = await createConversation()
        setConversations((current) => [conversation, ...current])
        setActiveId(conversation.id)
        conversationId = conversation.id
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to create conversation')
      return
    }

    const timestamp = Date.now()
    const assistantId = `pending-${timestamp}`
    setMessages((current) => [
      ...current,
      { id: `user-${timestamp}`, role: 'user', content, citations: [] },
      { id: assistantId, role: 'assistant', content: '', citations: [], streaming: true },
    ])
    setInput('')
    setSending(true)
    setError(null)
    setContextCount(null)

    const controller = new AbortController()
    abortRef.current = controller
    const started = performance.now()
    const updateAssistant = (patch: Partial<DisplayMessage>) => {
      setMessages((current) => current.map((message) => message.id === assistantId ? { ...message, ...patch } : message))
    }

    try {
      await sendChatMessage(
        conversationId,
        content,
        {
          onContext: (data) => setContextCount(data.context_chunks?.length ?? 0),
          onToken: (text) => {
            setMessages((current) => current.map((message) =>
              message.id === assistantId ? { ...message, content: message.content + text } : message,
            ))
          },
          onEnd: (data) => {
            updateAssistant({
              content: data.answer,
              citations: data.citations ?? [],
              answerMode: data.answer_mode,
              model: data.model,
              insufficientEvidence: data.insufficient_evidence,
              verification: data.verification ?? null,
              warnings: data.warnings ?? [],
              streaming: false,
              latency: performance.now() - started,
            })
          },
          onError: (message) => {
            updateAssistant({ streaming: false })
            setError(message)
          },
        },
        controller.signal,
      )
      updateAssistant({ streaming: false })
      listConversations().then(setConversations).catch(() => undefined)
    } catch (caught) {
      if ((caught as Error).name !== 'AbortError') setError(caught instanceof Error ? caught.message : 'Chat request failed')
      updateAssistant({ streaming: false })
    } finally {
      setSending(false)
      abortRef.current = null
    }
  }

  function onComposerKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void handleSend()
    }
  }

  return (
    <div className="nx-stack" style={{ gap: 16 }}>
      <div className="nx-row nx-row--between">
        <div>
          <p className="nx-eyebrow">Grounded workspace</p>
          <h1 className="nx-title" style={{ fontSize: 28 }}>Intelligence chat</h1>
          <p className="nx-subtitle" style={{ marginTop: 7 }}>
            One shared retrieval pipeline, evidence revalidated before generation, citations verified after.
          </p>
        </div>
        <div className="nx-row" style={{ gap: 8 }}>
          <Badge tone="success" dot>grounded</Badge>
          {contextCount !== null && <Badge tone="info">{contextCount} context chunk{contextCount === 1 ? '' : 's'}</Badge>}
        </div>
      </div>

      <div className="nx-chat">
        <aside className="nx-chat__rail">
          <div className="nx-chat__rail-head">
            <Button className="nx-btn--block" onClick={() => void handleNewConversation()}>
              <Plus size={14} /> New conversation
            </Button>
            <p className="nx-xs nx-muted" style={{ margin: '10px 0 0' }}>
              {conversations.length} conversation{conversations.length === 1 ? '' : 's'}
            </p>
          </div>
          <div className="nx-chat__list">
            {loadingList && <div className="nx-skeleton" style={{ height: 40 }} />}
            {!loadingList && conversations.length === 0 && (
              <p className="nx-xs nx-muted" style={{ padding: 10, lineHeight: 1.6 }}>No conversations yet. Start one to ask about your knowledge.</p>
            )}
            {conversations.map((conversation) => (
              <div key={conversation.id} style={{ position: 'relative' }}>
                <button
                  type="button"
                  onClick={() => setActiveId(conversation.id)}
                  className={cn('nx-chat__conv', activeId === conversation.id && 'is-active')}
                  style={{ width: '100%' }}
                >
                  <MessageSquare size={13} />
                  <span>{conversation.title || 'Untitled conversation'}</span>
                </button>
                <button
                  type="button"
                  onClick={() => void handleDeleteConversation(conversation.id)}
                  aria-label={`Delete ${conversation.title || 'conversation'}`}
                  style={{ position: 'absolute', right: 5, top: '50%', transform: 'translateY(-50%)', border: 0, background: 'transparent', color: 'var(--nx-faint)', width: 24, height: 24, display: 'grid', placeItems: 'center', borderRadius: 7 }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
          <div style={{ padding: 12, borderTop: '1px solid var(--nx-border)' }}>
            <div className="nx-row" style={{ gap: 7 }}>
              <span className="nx-dot nx-dot--success" />
              <span className="nx-xs nx-muted">RAG pipeline online</span>
            </div>
          </div>
        </aside>

        <section className="nx-chat__main">
          <header className="nx-chat__header">
            <div className="nx-row" style={{ gap: 9 }}>
              <span className="nx-avatar" style={{ width: 32, height: 32, borderRadius: 10 }}><Bot size={15} /></span>
              <div>
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>{activeConversation?.title || 'New conversation'}</p>
                <p className="nx-xs nx-muted" style={{ margin: '2px 0 0' }}>
                  {activeConversation ? `Updated ${timeAgo(activeConversation.updated_at)}` : 'Ask anything across your indexed knowledge'}
                </p>
              </div>
            </div>
            <div className="nx-row" style={{ gap: 6 }}>
              <Badge tone="violet"><Waypoints size={10} /> {retrievalMode} retrieval</Badge>
              {sending && <StatusBadge status="running" />}
            </div>
          </header>

          <div className="nx-chat__messages">
            {loadingMessages && (
              <div className="nx-stack">
                <div className="nx-skeleton" style={{ height: 58, width: '65%' }} />
                <div className="nx-skeleton" style={{ height: 88, width: '78%', marginLeft: 'auto' }} />
              </div>
            )}

            {!loadingMessages && messages.length === 0 && (
              <div style={{ margin: 'auto 0', width: '100%' }}>
                <EmptyState
                  icon={<Sparkles />}
                  title="Ask your organization's knowledge"
                  description="Every answer is grounded in permitted sources. If evidence is insufficient, Nexus says so instead of guessing."
                />
                <div className="nx-grid nx-grid--2" style={{ gap: 8, maxWidth: 700, margin: '4px auto 0' }}>
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => void handleSend(undefined, suggestion)}
                      className="nx-list-item"
                      style={{ textAlign: 'left', color: 'inherit' }}
                    >
                      <span className="nx-list-item__icon"><Sparkles /></span>
                      <span className="nx-list-item__body">
                        <span className="nx-list-item__title" style={{ whiteSpace: 'normal' }}>{suggestion}</span>
                      </span>
                      <ArrowUp size={13} className="nx-muted" style={{ transform: 'rotate(45deg)' }} />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} userInitials={userInitials} />
            ))}
            <div ref={bottomRef} />
          </div>

          <div className="nx-composer">
            {error && <div className="nx-error" style={{ marginBottom: 9 }}>{error}</div>}
            <form onSubmit={handleSend}>
              <div className="nx-composer__box">
                <span className="nx-avatar" style={{ width: 32, height: 32, margin: '0 0 2px 2px' }}><UserRound size={14} /></span>
                <textarea
                  value={input}
                  onChange={(event) => setInput(event.target.value)}
                  onKeyDown={onComposerKeyDown}
                  placeholder="Ask about your documents, sources or policies…"
                  rows={1}
                  disabled={sending}
                  aria-label="Message"
                />
                {sending ? (
                  <Button type="button" variant="danger" size="sm" onClick={stop} style={{ height: 38 }}>
                    <Square size={12} /> Stop
                  </Button>
                ) : (
                  <Button type="submit" size="sm" disabled={!input.trim()} style={{ height: 38, width: 38, padding: 0 }} aria-label="Send message">
                    <ArrowUp size={16} />
                  </Button>
                )}
              </div>
            </form>
            <div className="nx-row nx-row--between" style={{ marginTop: 8 }}>
              <span className="nx-xs nx-muted">Enter to send · Shift+Enter for a new line</span>
              <span className="nx-xs nx-muted" style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <CheckCircle2 size={11} /> permissions enforced before generation
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
