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
  task_id?: string | null
  worker?: string | null
  error_message: string | null
  started_at?: string | null
  finished_at?: string | null
  created_at: string
  updated_at: string
}

export interface Document {
  id: string
  organization_id?: string
  uploaded_by?: string | null
  filename: string
  content_type: string
  file_size: number
  storage_backend?: string | null
  status: 'pending' | 'processing' | 'completed' | 'failed'
  error_message: string | null
  retry_count?: number
  metadata?: Record<string, unknown>
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
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'waiting_for_approval'
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
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'waiting_for_approval'
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
  organization_id?: string
  user_id?: string | null
  execution_id?: string | null
  title: string
  report_type: string
  file_format: string
  status: string
  storage_key?: string | null
  error?: string | null
  created_at: string
}

export interface ExtractedDocument {
  document_id: string
  filename: string
  text: string
  metadata: Record<string, unknown>
  spans: Array<Record<string, unknown>>
  warnings: string[]
  dates: string[]
  entities: string[]
  obligations: string[]
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
  documents: Array<{
    document_id: string
    filename: string
    dates: string[]
    entities: string[]
    obligations: string[]
    spans: Array<Record<string, unknown>>
  }>
  comparisons: Array<{
    document_id: string
    filename: string
    changed_lines: string[]
  }>
  citations: Array<Record<string, unknown>>
}

export interface AgentCatalogItem {
  id: string
  name: string
  description: string
  capabilities: string[]
  required_permissions: string[]
  tools: string[]
}

export interface SystemCapabilities {
  providers: {
    llm: { provider: string; embedding_provider?: string; llm_provider?: string; available: boolean; extractive_fallback: boolean; model: string }
    embeddings: { provider: string; model: string; dimensions: number | null; semantic: boolean }
    vector: { backend: string; collection: string }
    storage: { backend: string }
  }
  retrieval: Record<string, unknown>
  chunking: Record<string, unknown>
  verification: Record<string, unknown>
  worker: { celery_enabled: boolean; max_ingestion_retries: number }
  connectors: string[]
  warnings: string[]
  organization_id: string
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
      const body = await response.json() as { error?: { message?: string }; detail?: { message?: string } | string }
      message =
        body.error?.message ??
        (typeof body.detail === 'string' ? body.detail : body.detail?.message) ??
        message
    } catch {
      // Preserve the HTTP error when the server does not return JSON.
    }
    if (response.status === 401) {
      sessionStorage.removeItem('nexus_access_token')
      window.dispatchEvent(new Event('nexus:unauthorized'))
    }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  const text = await response.text()
  if (!text) return undefined as T
  return JSON.parse(text) as T
}

export async function getCurrentUser(): Promise<User> {
  return apiRequest<User>('/auth/me')
}

export async function updateCurrentUser(payload: { full_name?: string; email?: string }): Promise<User> {
  return apiRequest<User>('/auth/me', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<{ message: string }> {
  return apiRequest('/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
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
  maxRows = 100,
): Promise<AgentExecution> {
  return apiRequest<AgentExecution>('/agents/executions', {
    method: 'POST',
    body: JSON.stringify({ request, source_id: sourceId ?? null, sql: sql || null, max_rows: maxRows }),
  })
}

export async function listExecutionSteps(id: string): Promise<AgentExecutionStep[]> {
  return apiRequest<AgentExecutionStep[]>(`/agents/executions/${id}/steps`)
}

export async function cancelAgentExecution(id: string): Promise<AgentExecution> {
  return apiRequest<AgentExecution>(`/agents/executions/${id}/cancel`, { method: 'POST' })
}

export async function retryAgentExecution(id: string): Promise<AgentExecution> {
  return apiRequest<AgentExecution>(`/agents/executions/${id}/retry`, { method: 'POST' })
}

export async function agentCatalog(): Promise<AgentCatalogItem[]> {
  return apiRequest<AgentCatalogItem[]>('/agents/catalog')
}

export async function systemCapabilities(): Promise<SystemCapabilities> {
  return apiRequest<SystemCapabilities>('/system/capabilities')
}

export interface DatabaseColumn {
  name: string
  type: string
  nullable: boolean
}

export interface DatabaseTable {
  schema: string
  table: string
  columns: DatabaseColumn[]
  primary_key: string[]
}

export interface DatabaseSchema {
  driver: string
  tables: DatabaseTable[]
  truncated: boolean
}

export async function databaseSchema(sourceId: string): Promise<DatabaseSchema> {
  return apiRequest<DatabaseSchema>(`/agents/sql/schema?source_id=${encodeURIComponent(sourceId)}`, { method: 'POST' })
}

export async function generateSql(sourceId: string, question: string): Promise<{ sql: string; explanation: string; schema: DatabaseSchema }> {
  return apiRequest('/agents/sql/generate', {
    method: 'POST',
    body: JSON.stringify({ source_id: sourceId, question }),
  })
}

export async function validateSql(sql: string, maxRows = 100): Promise<{ valid: boolean; sql: string }> {
  return apiRequest('/agents/sql/validate', {
    method: 'POST',
    body: JSON.stringify({ sql, max_rows: maxRows }),
  })
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

export async function extractDocument(documentId: string): Promise<ExtractedDocument> {
  return apiRequest<ExtractedDocument>(`/intelligence/documents/${documentId}/extract`)
}

export async function compareDocuments(documentIds: string[]): Promise<DocumentComparison> {
  return apiRequest<DocumentComparison>('/intelligence/documents/compare', {
    method: 'POST',
    body: JSON.stringify({ document_ids: documentIds }),
  })
}

export async function deleteReport(reportId: string): Promise<void> {
  await apiRequest(`/intelligence/reports/${reportId}`, { method: 'DELETE' })
}

export async function downloadReport(report: ReportMetadata): Promise<void> {
  const headers = new Headers()
  const accessToken = token()
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const response = await fetch(`${API_BASE_URL}/intelligence/reports/${encodeURIComponent(report.id)}/download`, { headers })
  if (!response.ok) {
    let message = `Download failed (${response.status})`
    try {
      const body = await response.json() as { error?: { message?: string }; detail?: { message?: string } | string }
      message = body.error?.message ?? (typeof body.detail === 'string' ? body.detail : body.detail?.message) ?? message
    } catch {
      // Keep the HTTP status when the error response is not JSON.
    }
    if (response.status === 401) {
      sessionStorage.removeItem('nexus_access_token')
      window.dispatchEvent(new Event('nexus:unauthorized'))
    }
    throw new Error(message)
  }
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  const extension = report.file_format === 'markdown' ? 'md' : report.file_format
  const safeTitle = (report.title || 'nexus-report').replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 80)
  anchor.href = objectUrl
  anchor.download = `${safeTitle || 'nexus-report'}.${extension}`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(objectUrl)
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

export async function health(): Promise<{ status: string; services: Record<string, string>; version?: string }> {
  return apiRequest('/health')
}

// ---------------------------------------------------------------------------
// Administration (organization-scoped, read-only)
// ---------------------------------------------------------------------------

export interface AdminOverview {
  organization: { id: string; name: string | null }
  counts: Record<string, number>
  role: string | null
}

export interface AdminUser {
  id: string
  email: string
  full_name: string | null
  role: string | null
  is_active: boolean
  created_at: string
}

export interface AuditLogEntry {
  id: string
  user_id: string | null
  action: string
  resource_type: string | null
  resource_id: string | null
  details: string | null
  created_at: string
}

export async function adminOverview(): Promise<AdminOverview> {
  return apiRequest<AdminOverview>('/admin/overview')
}

export async function adminUsers(limit = 100, offset = 0): Promise<{ items: AdminUser[] }> {
  return apiRequest(`/admin/users?limit=${limit}&offset=${offset}`)
}

export async function adminAuditLogs(limit = 100): Promise<{ items: AuditLogEntry[] }> {
  return apiRequest(`/admin/audit-logs?limit=${limit}`)
}

// ---------------------------------------------------------------------------
// Analytics
// ---------------------------------------------------------------------------

export interface AnalyticsOverview {
  window_days: number
  generated_at: string
  queries: {
    total_all_time: number
    window: number
    successful: number
    no_evidence: number
    success_rate: number | null
    avg_latency_ms: number | null
    p95_latency_ms: number | null
    avg_retrieval_ms: number | null
  }
  series: Array<{
    date: string
    queries: number
    avg_retrieval_ms: number
    avg_total_ms: number
    no_evidence: number
  }>
  distribution: {
    answer_modes: Record<string, number>
    verification: Record<string, number>
    retrieval_modes: Record<string, number>
  }
  agents: { total: number; by_status: Record<string, number>; avg_duration_ms: number | null }
  knowledge: {
    documents_by_status: Record<string, number>
    documents_total: number
    chunks: number
    sources: number
    active_sources: number
  }
  activity: {
    conversations: number
    reports: number
    pending_approvals: number
    active_ingestions: number
  }
  evaluation: {
    run_id: string | null
    name: string | null
    dataset: string | null
    item_count: number | null
    metrics: Record<string, number>
    created_at: string | null
  }
}

export async function analyticsOverview(days = 14): Promise<AnalyticsOverview> {
  return apiRequest<AnalyticsOverview>(`/analytics/overview?days=${days}`)
}

// ---------------------------------------------------------------------------
// Chat / RAG (POST-based SSE via fetch ReadableStream; EventSource cannot POST)
// ---------------------------------------------------------------------------

export interface Citation {
  index: number
  chunk_id: string
  document_id: string
  document_filename: string
  document_title?: string
  citation_id?: string
  page_number?: number | null
  section_heading?: string | null
  source_type?: string
  provenance: Array<{ kind: string; number?: number; row?: number; sheet?: string }>
  score: number
  text: string
}

export interface RagVerificationClaim {
  claim: string
  status: 'supported' | 'partially_supported' | 'unsupported' | 'conflicting_evidence' | 'insufficient_evidence'
  citation_indices: number[]
  support_score: number
  reasons: string[]
  unsupported_numbers?: string[]
}

export interface RagVerification {
  status: 'supported' | 'partially_supported' | 'unsupported' | 'conflicting_evidence' | 'insufficient_evidence'
  claims?: RagVerificationClaim[]
  unsupported_claims: string[]
  conflicting_claims: string[]
  insufficient_claims: string[]
  citation_errors: string[]
  evidence_coverage: number
  method: string
  disclaimer: string
}

export interface RagEvidence {
  chunk_id: string
  document_id: string
  organization_id: string
  document_filename: string
  text: string
  score: number
  mode: string
  provenance: Array<Record<string, unknown>>
  section_heading?: string | null
  document_version: number
  source_type?: string | null
  char_start: number
  char_end: number
  content_hash: string
  retrieval_rank: number
  rerank_score?: number | null
  retrieval_scores: Record<string, number>
}

export interface RagQueryResponse {
  answer: string
  answer_mode: 'llm' | 'extractive' | 'no_evidence'
  model: string
  citations: Citation[]
  evidence: RagEvidence[]
  verification: RagVerification | null
  query_analysis: Record<string, unknown>
  timings: Record<string, number>
  trace_id: string
  insufficient_evidence: boolean
  warnings: string[]
  retrieval_mode: string
  reranker: string | null
  degraded_from: string | null
  context_chunk_count: number
}

export interface RagIngestionJob {
  job_id: string
  document_id: string
  status: string
  attempt: number
  max_attempts: number
  error: string | null
  document_status: string | null
  document_version: number | null
  metadata: Record<string, unknown>
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface RagIngestResponse {
  document: {
    id: string
    filename: string
    status: string
    version: number
    access_scope: string | null
    chunk_count?: number
  }
  job: RagIngestionJob
}

export interface RagStatus {
  organization_id: string
  documents: { total: number; by_status: Record<string, number>; chunks: number }
  index: Record<string, unknown>
  sync: { sampled_documents: number; out_of_sync: Array<Record<string, unknown>> }
  pipeline_version?: string
  capabilities: { modes: string[]; default_mode?: string; verification: boolean; reranker: string }
}

export interface RagSourceDocument {
  id: string
  filename: string
  content_type: string
  status: string
  version: number
  access_scope: string | null
  source_id: string | null
  chunk_count: number
  updated_at: string
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
    verification?: RagVerification | null
    trace_id?: string
    warnings?: string[]
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
    verification?: RagVerification | null
    trace_id?: string
    warnings?: string[]
    timings?: Record<string, number>
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

// ---------------------------------------------------------------------------
// RAG console: query, retrieval diagnostics, ingestion and index management
// ---------------------------------------------------------------------------

export interface RagQueryOptions {
  mode?: 'hybrid' | 'dense' | 'sparse'
  topK?: number
  documentIds?: string[]
  sourceTypes?: string[]
  rerank?: boolean
  verify?: boolean
  includeEvidence?: boolean
}

export async function ragQuery(query: string, options: RagQueryOptions = {}): Promise<RagQueryResponse> {
  return apiRequest<RagQueryResponse>('/rag/query', {
    method: 'POST',
    body: JSON.stringify({
      query,
      mode: options.mode ?? null,
      top_k: options.topK ?? null,
      rerank: options.rerank ?? null,
      verify: options.verify ?? null,
      include_evidence: options.includeEvidence ?? true,
      filters: {
        document_ids: options.documentIds ?? [],
        source_types: options.sourceTypes ?? [],
      },
    }),
  })
}

export async function ragRetrievalTest(query: string, options: RagQueryOptions = {}): Promise<{
  query: string
  mode: string
  queries_used: string[]
  reranker: string | null
  timings: Record<string, number>
  warnings: string[]
  evidence: RagEvidence[]
}> {
  return apiRequest('/rag/retrieval/test', {
    method: 'POST',
    body: JSON.stringify({
      query,
      mode: options.mode ?? null,
      top_k: options.topK ?? null,
      rerank: options.rerank ?? null,
      include_text: true,
      filters: {
        document_ids: options.documentIds ?? [],
        source_types: options.sourceTypes ?? [],
      },
    }),
  })
}

export async function ragIngestText(input: {
  content: string
  filename?: string
  title?: string
  accessScope?: 'organization' | 'private' | 'admin'
  sourceId?: string
}): Promise<RagIngestResponse> {
  return apiRequest<RagIngestResponse>('/rag/ingest', {
    method: 'POST',
    body: JSON.stringify({
      content: input.content,
      filename: input.filename || 'note.txt',
      title: input.title ?? null,
      access_scope: input.accessScope ?? 'organization',
      source_id: input.sourceId ?? null,
      metadata: {},
    }),
  })
}

export async function ragIngestionStatus(jobId: string): Promise<RagIngestionJob> {
  return apiRequest<RagIngestionJob>(`/rag/ingestions/${jobId}`)
}

export async function ragReindexDocument(documentId: string): Promise<RagIngestResponse> {
  return apiRequest<RagIngestResponse>(`/rag/documents/${documentId}/reindex`, { method: 'POST' })
}

export async function ragDeleteDocumentIndex(documentId: string): Promise<{
  document_id: string
  deleted_chunks: number
  deleted_points: number
  vector_error: string | null
}> {
  return apiRequest(`/rag/documents/${documentId}/index`, { method: 'DELETE' })
}

export async function ragStatus(): Promise<RagStatus> {
  return apiRequest<RagStatus>('/rag/status')
}

export async function ragSources(): Promise<{
  documents: RagSourceDocument[]
  connectors: Array<Record<string, unknown>>
}> {
  return apiRequest('/rag/sources')
}

export async function ragRunEvaluation(input: {
  name?: string
  items: Array<{ query: string; relevant_chunk_ids?: string[]; relevant_document_ids?: string[] }>
  k?: number
  generate?: boolean
}): Promise<Record<string, unknown>> {
  return apiRequest('/rag/evaluation/run', {
    method: 'POST',
    body: JSON.stringify({ ...input, persist: true }),
  })
}

export interface RagEvaluationSummary {
  id: string
  name?: string | null
  dataset_name?: string | null
  mode?: string | null
  k?: number | null
  item_count?: number | null
  metrics?: Record<string, number>
  created_at: string
}

export async function ragEvaluations(): Promise<{ items: RagEvaluationSummary[] }> {
  return apiRequest('/rag/evaluations')
}

export async function ragEvaluation(runId: string): Promise<Record<string, unknown>> {
  return apiRequest(`/rag/evaluations/${runId}`)
}

export async function ragConfig(): Promise<Record<string, unknown>> {
  return apiRequest('/rag/config')
}

export async function ragHealth(): Promise<Record<string, unknown>> {
  return apiRequest('/rag/health')
}

export async function ragDeleteDocument(documentId: string): Promise<Record<string, unknown>> {
  return apiRequest(`/rag/documents/${documentId}`, { method: 'DELETE' })
}

export async function ragDocumentSync(documentId: string): Promise<Record<string, unknown>> {
  return apiRequest(`/rag/documents/${documentId}/sync`)
}
