import React from 'react'
import { Button, Card, Input } from '@/components/ui'
import {
  ChatMessage,
  Citation,
  Conversation,
  createConversation,
  deleteConversation,
  listConversations,
  listMessages,
  sendChatMessage,
} from '@/src/api'

interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  answerMode?: string
  insufficientEvidence?: boolean
  streaming?: boolean
}

function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null
  return (
    <div className='mt-3 border-t border-border pt-3'>
      <p className='text-xs font-medium text-muted-foreground mb-2'>Sources ({citations.length})</p>
      <ul className='space-y-2'>
        {citations.map((c) => {
          const page = c.provenance?.find((p) => p.kind === 'page' && p.number)?.number
          return (
            <li key={`${c.index}-${c.chunk_id}`} className='text-xs text-muted-foreground'>
              <span className='font-medium text-foreground'>
                [{c.index}] {c.document_filename}
                {page ? ` (p. ${page})` : ''}
              </span>
              <span className='ml-2 line-clamp-2'>{c.text.slice(0, 160)}{c.text.length > 160 ? '…' : ''}</span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function MessageBubble({ message }: { message: DisplayMessage }) {
  if (message.role === 'user') {
    return (
      <div className='flex justify-end'>
        <div className='max-w-[75%] rounded-lg bg-primary text-primary-foreground px-4 py-2.5 text-sm whitespace-pre-wrap'>
          {message.content}
        </div>
      </div>
    )
  }
  return (
    <div className='flex justify-start'>
      <div className='max-w-[85%] rounded-lg border border-border bg-card px-4 py-2.5 text-sm'>
        <div className='whitespace-pre-wrap'>{message.content}</div>
        {message.streaming && (
          <span className='inline-block h-3 w-2 animate-pulse bg-muted-foreground ml-1 align-middle' />
        )}
        {message.insufficientEvidence && (
          <p className='mt-2 text-xs text-amber-600'>
            No sufficiently relevant knowledge was found for this question.
          </p>
        )}
        {message.answerMode && !message.streaming && (
          <p className='mt-2 text-[10px] uppercase tracking-wide text-muted-foreground'>
            {message.answerMode === 'llm' ? 'Generated answer' : message.answerMode === 'extractive' ? 'Extractive answer (no LLM configured)' : message.answerMode.replace('_', ' ')}
            {message.insufficientEvidence ? ' · insufficient evidence' : ''}
          </p>
        )}
        <CitationList citations={message.citations} />
      </div>
    </div>
  )
}

export default function ChatWorkspace() {
  const [conversations, setConversations] = React.useState<Conversation[]>([])
  const [activeId, setActiveId] = React.useState<string | null>(null)
  const [messages, setMessages] = React.useState<DisplayMessage[]>([])
  const [input, setInput] = React.useState('')
  const [sending, setSending] = React.useState(false)
  const [loadingList, setLoadingList] = React.useState(true)
  const [loadingMessages, setLoadingMessages] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const abortRef = React.useRef<AbortController | null>(null)
  const bottomRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    listConversations()
      .then((list) => {
        setConversations(list)
        if (list.length) setActiveId((current) => current ?? list[0].id)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load conversations'))
      .finally(() => setLoadingList(false))
  }, [])

  React.useEffect(() => {
    if (!activeId) { setMessages([]); return }
    let cancelled = false
    setLoadingMessages(true)
    listMessages(activeId)
      .then((history) => {
        if (cancelled) return
        setMessages(history.map((m: ChatMessage) => ({
          id: m.id,
          role: m.role,
          content: m.content,
          citations: m.citations ?? [],
          answerMode: m.meta?.answer_mode,
          insufficientEvidence: m.meta?.insufficient_evidence,
        })))
      })
      .catch((e) => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load messages') })
      .finally(() => { if (!cancelled) setLoadingMessages(false) })
    return () => { cancelled = true }
  }, [activeId])

  React.useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleNewConversation() {
    try {
      const conv = await createConversation()
      setConversations((current) => [conv, ...current])
      setActiveId(conv.id)
      setMessages([])
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create conversation')
    }
  }

  async function handleDeleteConversation(id: string) {
    try {
      await deleteConversation(id)
      setConversations((current) => current.filter((c) => c.id !== id))
      if (activeId === id) { setActiveId(null); setMessages([]) }
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete conversation')
    }
  }

  async function handleSend(event: React.FormEvent) {
    event.preventDefault()
    const content = input.trim()
    if (!content || sending) return
    let conversationId = activeId
    try {
      if (!conversationId) {
        const conv = await createConversation()
        setConversations((current) => [conv, ...current])
        setActiveId(conv.id)
        conversationId = conv.id
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create conversation')
      return
    }

    const assistantId = `pending-${Date.now()}`
    setMessages((current) => [
      ...current,
      { id: `user-${Date.now()}`, role: 'user', content, citations: [] },
      { id: assistantId, role: 'assistant', content: '', citations: [], streaming: true },
    ])
    setInput('')
    setSending(true)
    setError(null)

    const controller = new AbortController()
    abortRef.current = controller
    const updateAssistant = (patch: Partial<DisplayMessage>) => {
      setMessages((current) => current.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)))
    }

    try {
      await sendChatMessage(
        conversationId,
        content,
        {
          onToken: (text) => {
            setMessages((current) => current.map((m) =>
              m.id === assistantId ? { ...m, content: m.content + text } : m,
            ))
          },
          onEnd: (data) => {
            updateAssistant({
              id: assistantId,
              content: data.answer,
              citations: data.citations ?? [],
              answerMode: data.answer_mode,
              insufficientEvidence: data.insufficient_evidence,
              streaming: false,
            })
          },
          onError: (message) => {
            updateAssistant({ streaming: false })
            setError(message)
          },
        },
        controller.signal,
      )
      // Safety: clear streaming flag if stream ended without message_end.
      updateAssistant({ streaming: false })
      // Refresh conversation ordering (updated_at changes on new messages).
      listConversations().then(setConversations).catch(() => undefined)
    } catch (e) {
      updateAssistant({ streaming: false })
      setError(e instanceof Error ? e.message : 'Chat request failed')
    } finally {
      setSending(false)
      abortRef.current = null
    }
  }

  return (
    <div className='grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-6'>
      <Card title='Conversations'>
        <Button variant='outline' size='sm' className='w-full mb-4' onClick={handleNewConversation}>
          New chat
        </Button>
        {loadingList && <p className='text-sm text-muted-foreground'>Loading…</p>}
        <ul className='space-y-1'>
          {conversations.map((conv) => (
            <li key={conv.id} className='flex items-center gap-1'>
              <button
                type='button'
                onClick={() => setActiveId(conv.id)}
                className={`flex-1 truncate rounded-md px-3 py-2 text-left text-sm hover:bg-accent ${
                  activeId === conv.id ? 'bg-accent font-medium' : ''
                }`}
              >
                {conv.title ?? 'Untitled chat'}
              </button>
              <Button
                variant='ghost'
                size='sm'
                className='text-xs text-muted-foreground'
                onClick={() => handleDeleteConversation(conv.id)}
              >
                ✕
              </Button>
            </li>
          ))}
        </ul>
        {!loadingList && conversations.length === 0 && (
          <p className='text-sm text-muted-foreground'>No conversations yet. Start a new chat.</p>
        )}
      </Card>

      <Card title='Chat workspace'>
        <div className='flex flex-col gap-4 min-h-[420px]'>
          <div className='flex-1 space-y-4 overflow-y-auto max-h-[60vh]'>
            {loadingMessages && <p className='text-sm text-muted-foreground'>Loading messages…</p>}
            {!loadingMessages && messages.length === 0 && (
              <p className='text-sm text-muted-foreground text-center py-12'>
                Ask a question about your indexed documents. Answers are grounded in retrieved sources with citations.
              </p>
            )}
            {messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            <div ref={bottomRef} />
          </div>

          {error && <p className='text-sm text-red-600'>{error}</p>}

          <form className='flex gap-2' onSubmit={handleSend}>
            <Input
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder='Ask a question about your knowledge sources…'
              disabled={sending}
            />
            <Button type='submit' disabled={sending || !input.trim()}>
              {sending ? 'Sending…' : 'Send'}
            </Button>
          </form>
        </div>
      </Card>
    </div>
  )
}
