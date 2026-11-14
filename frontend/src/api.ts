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

export async function health(): Promise<{ status: string; services: Record<string, string> }> {
  return apiRequest('/health')
}
