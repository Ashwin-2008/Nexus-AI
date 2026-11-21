export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export interface User {
  id: string
  email: string
  full_name: string | null
  is_active: boolean
  organization_id: string
  role: string
  created_at: string
}

export interface IngestionJob {
  id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'retrying'
  attempt: number
  max_attempts: number
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface Document {
  id: string
  filename: string
  content_type: string
  file_size: number
  status: 'pending' | 'processing' | 'completed' | 'failed'
  error_message: string | null
  latest_job: IngestionJob | null
  created_at: string
  updated_at: string
}

export type ConnectorType = 'postgres' | 'mysql' | 'rest' | 'website' | 'github' | 'gdrive' | 'email'

export interface DataSource {
  id: string
  name: string
  type: ConnectorType
  status: 'active' | 'error' | 'disabled'
  config: Record<string, unknown>
  credentials_masked: Record<string, unknown> | null
  last_synced_at: string | null
  last_sync_status: string | null
  last_error: string | null
  created_at: string
  updated_at: string
}

export interface SyncJob {
  id: string
  data_source_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  fetched: number
  ingested: number
  skipped: number
  failed: number
  error: string | null
  started_at: string
  finished_at: string | null
}

export interface SearchHit {
  chunk_id: string
  document_id: string
  document_filename: string
  chunk_index: number
  text: string
  provenance: Array<Record<string, unknown>>
  score: number
  mode: string
  metadata: Record<string, unknown>
}

export interface SearchResponse {
  query: string
  mode: 'semantic' | 'lexical' | 'hybrid'
  total: number
  hits: SearchHit[]
}

export interface AgentExecution {
  id: string
  agent_type: string
  status: 'queued' | 'running' | 'succeeded' | 'failed'
  request: string
  plan: Record<string, unknown>
  result: Record<string, unknown> | null
  error: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface AgentExecutionStep {
  id: string
  agent_id: string
  step_key: string
  status: string
  description: string
  output_summary: Record<string, unknown> | null
  error: string | null
  started_at: string | null
  finished_at: string | null
}

export interface AgentApproval {
  id: string
  execution_id: string
  step_id: string | null
  agent_id: string
  action: string
  action_summary: string
  risk_level: string
  requested_permissions: string[]
  status: string
  rejection_reason: string | null
  requested_at: string
  decided_at: string | null
  expires_at: string | null
}

export interface ReportMetadata {
  id: string
  title: string
  report_type: string
  file_format: string
  status: string
  storage_key?: string | null
  created_at: string
}

export interface EmailSearchResult {
  source_id: string
  query: string
  count: number
  messages: Array<{
    external_id: string
    subject: string
    body: string
    uri: string | null
    metadata: Record<string, unknown>
  }>
}

export interface DocumentComparison {
  documents: Array<Record<string, unknown>>
  comparisons: Array<Record<string, unknown>>
  citations: Array<Record<string, unknown>>
}

function token(): string | null {
  return sessionStorage.getItem('nexus_access_token')
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (!headers.has('Content-Type') && init.body && !(init.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  const accessToken = token()
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)

  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
  if (!response.ok) {
    let message = `Request failed (${response.status})`
    try {
      const body = await response.json() as { error?: { message?: string } }
      message = body.error?.message ?? message
    } catch {
      // Preserve the HTTP error when the server does not return JSON.
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export async function getCurrentUser(): Promise<User> {
  return apiRequest<User>('/auth/me')
}

export async function login(email: string, password: string): Promise<User> {
  const result = await apiRequest<{ access_token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  sessionStorage.setItem('nexus_access_token', result.access_token)
  return getCurrentUser()
}

export async function register(email: string, password: string, fullName: string, organizationName: string): Promise<User> {
  return apiRequest<User>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, full_name: fullName || null, organization_name: organizationName }),
  })
}

export function logout(): void {
  sessionStorage.removeItem('nexus_access_token')
}

export async function listDocuments(): Promise<Document[]> {
  const result = await apiRequest<{ items: Document[] }>('/documents')
  return result.items
}

export async function uploadDocument(file: File): Promise<Document> {
  const body = new FormData()
  body.append('file', file)
  return apiRequest<Document>('/documents/upload', { method: 'POST', body })
}

export async function retryDocument(id: string): Promise<Document> {
  return apiRequest<Document>(`/documents/${id}/retry`, { method: 'POST' })
}

export async function listSources(): Promise<DataSource[]> {
  return apiRequest<DataSource[]>('/sources')
}

export async function createSource(
  name: string,
  type: ConnectorType,
  config: Record<string, unknown>,
  credentials: Record<string, unknown>,
): Promise<DataSource> {
  return apiRequest<DataSource>('/sources', {
    method: 'POST',
    body: JSON.stringify({ name, type, config, credentials }),
  })
}

export async function testSource(id: string): Promise<{ ok: boolean; type?: string; error?: string }> {
  return apiRequest(`/sources/${id}/test`, { method: 'POST' })
}

export async function syncSource(id: string): Promise<SyncJob> {
  return apiRequest<SyncJob>(`/sources/${id}/sync`, { method: 'POST' })
}

export async function listSourceSyncs(id: string): Promise<SyncJob[]> {
  return apiRequest<SyncJob[]>(`/sources/${id}/syncs`)
}

export async function deleteSource(id: string): Promise<void> {
  await apiRequest(`/sources/${id}`, { method: 'DELETE' })
}

export async function searchKnowledge(
  query: string,
  mode: SearchResponse['mode'] = 'hybrid',
  topK = 8,
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, mode, top_k: String(topK) })
  return apiRequest<SearchResponse>(`/search?${params.toString()}`)
}

export async function listAgentExecutions(limit = 50): Promise<AgentExecution[]> {
  return apiRequest<AgentExecution[]>(`/agents/executions?limit=${limit}`)
}

export async function createAgentExecution(
  request: string,
  sourceId?: string,
  sql?: string,
): Promise<AgentExecution> {
  return apiRequest<AgentExecution>('/agents/executions', {
    method: 'POST',
    body: JSON.stringify({ request, source_id: sourceId ?? null, sql: sql || null }),
  })
}

export async function listExecutionSteps(id: string): Promise<AgentExecutionStep[]> {
  return apiRequest<AgentExecutionStep[]>(`/agents/executions/${id}/steps`)
}

export async function listPendingApprovals(): Promise<AgentApproval[]> {
  return apiRequest<AgentApproval[]>('/agents/approvals?pending_only=true')
}

export async function approveAgentAction(id: string): Promise<AgentApproval> {
  return apiRequest<AgentApproval>(`/agents/approvals/${id}/approve`, { method: 'POST' })
}

export async function rejectAgentAction(id: string, reason: string): Promise<AgentApproval> {
  return apiRequest<AgentApproval>(`/agents/approvals/${id}/reject`, {
    method: 'POST',
    body: JSON.stringify({ rejection_reason: reason }),
  })
}

export async function searchEmail(sourceId: string, query: string, maxItems = 20): Promise<EmailSearchResult> {
  return apiRequest<EmailSearchResult>('/intelligence/email/search', {
    method: 'POST',
    body: JSON.stringify({ source_id: sourceId, query, max_items: maxItems }),
  })
}

export async function createEmailDraft(
  sourceId: string,
  recipients: string[],
  subject: string,
  body: string,
  attachments: Array<Record<string, string>> = [],
): Promise<{ execution_id: string; approval_id: string; status: string }> {
  return apiRequest('/intelligence/email/draft', {
    method: 'POST',
    body: JSON.stringify({ source_id: sourceId, recipients, subject, body, attachments }),
  })
}

export async function listReports(): Promise<ReportMetadata[]> {
  return apiRequest('/intelligence/reports')
}

export async function compareDocuments(documentIds: string[]): Promise<DocumentComparison> {
  return apiRequest<DocumentComparison>('/intelligence/documents/compare', {
    method: 'POST',
    body: JSON.stringify({ document_ids: documentIds }),
  })
}

export async function exportReport(reportId: string, report: Record<string, unknown>, format: 'pdf' | 'docx' | 'xlsx' | 'csv') {
  return apiRequest<{ report_id: string; format: string; storage_key: string; size: number }>('/intelligence/reports/export', {
    method: 'POST',
    body: JSON.stringify({ report_id: reportId, report, format }),
  })
}

export function reportDownloadUrl(reportId: string, format: 'pdf' | 'docx' | 'xlsx' | 'csv'): string {
  const base = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
  return `${base}/intelligence/reports/${encodeURIComponent(reportId)}?format=${format}`
}

export async function health(): Promise<{ status: string; services: Record<string, string> }> {
  return apiRequest('/health')
}

// ---------------------------------------------------------------------------
// Chat / RAG (POST-based SSE via fetch ReadableStream; EventSource cannot POST)
// ---------------------------------------------------------------------------

export interface Citation {
  index: number
  chunk_id: string
  document_id: string
  document_filename: string
  provenance: Array<{ kind: string; number?: number; row?: number; sheet?: string }>
  score: number
  text: string
}

export interface Conversation {
  id: string
  title: string | null
  user_id: string
  organization_id: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  citations: Citation[]
  meta: {
    answer_mode?: 'llm' | 'extractive' | 'no_evidence'
    model?: string
    retrieval_latency_ms?: number
    generation_latency_ms?: number
    insufficient_evidence?: boolean
    degraded_from?: string
  }
  created_at: string
}

export interface StreamHandlers {
  onStart?: (data: { conversation_id: string; user_message_id: string }) => void
  onContext?: (data: { retrieval_latency_ms: number; context_chunks: Citation[] }) => void
  onToken?: (text: string) => void
  onEnd: (data: {
    answer: string
    answer_mode: string
    model?: string
    citations: Citation[]
    insufficient_evidence?: boolean
    degraded_from?: string
  }) => void
  onError: (message: string) => void
}

export async function listConversations(): Promise<Conversation[]> {
  return apiRequest<Conversation[]>('/chat/conversations')
}

export async function createConversation(title?: string): Promise<Conversation> {
  return apiRequest<Conversation>('/chat/conversations', {
    method: 'POST',
    body: JSON.stringify({ title: title ?? null }),
  })
}

export async function deleteConversation(id: string): Promise<void> {
  await apiRequest(`/chat/conversations/${id}`, { method: 'DELETE' })
}

export async function listMessages(conversationId: string): Promise<ChatMessage[]> {
  return apiRequest<ChatMessage[]>(`/chat/conversations/${conversationId}/messages`)
}

function authHeader(): string | null {
  const accessToken = token()
  return accessToken ? `Bearer ${accessToken}` : null
}

/**
 * Send a chat message and stream the assistant answer as SSE events.
 * Uses fetch + ReadableStream (POST bodies are not possible with EventSource).
 */
export async function sendChatMessage(
  conversationId: string,
  content: string,
  handlers: StreamHandlers,
  abortSignal?: AbortSignal,
): Promise<void> {
  const headers = new Headers({ 'Content-Type': 'application/json' })
  const bearer = authHeader()
  if (bearer) headers.set('Authorization', bearer)

  const response = await fetch(`${API_BASE_URL}/chat/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ content, stream: true }),
    signal: abortSignal,
  })

  if (!response.ok || !response.body) {
    let message = `Chat request failed (${response.status})`
    try {
      const body = await response.json() as { error?: { message?: string }; detail?: { message?: string } }
      message = body.error?.message ?? body.detail?.message ?? message
    } catch {
      // Non-JSON error (e.g. nginx HTML) — keep generic message.
    }
    handlers.onError(message)
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const dispatch = (block: string): void => {
    let eventName = ''
    let dataRaw = ''
    for (const line of block.split('\n')) {
      if (line.startsWith('event: ')) eventName = line.slice(7).trim()
      else if (line.startsWith('data: ')) dataRaw += line.slice(6)
    }
    if (!eventName || !dataRaw) return
    let data: unknown
    try {
      data = JSON.parse(dataRaw)
    } catch {
      return
    }
    switch (eventName) {
      case 'message_start':
        handlers.onStart?.(data as { conversation_id: string; user_message_id: string })
        break
      case 'context':
        handlers.onContext?.(data as { retrieval_latency_ms: number; context_chunks: Citation[] })
        break
      case 'token':
        handlers.onToken?.((data as { text: string }).text)
        break
      case 'message_end':
        handlers.onEnd(data as Parameters<StreamHandlers['onEnd']>[0])
        break
      case 'error':
        handlers.onError((data as { message?: string }).message ?? 'Generation failed')
        break
      default:
        break
    }
  }

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let separator: number
      // SSE events are separated by a blank line.
      while ((separator = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, separator)
        buffer = buffer.slice(separator + 2)
        if (block.trim()) dispatch(block)
      }
    }
    if (buffer.trim()) dispatch(buffer)
  } catch (error) {
    if ((error as Error).name === 'AbortError') return
    handlers.onError((error as Error).message || 'Streaming failed')
  }
}
