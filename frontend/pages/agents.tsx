import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  FileText,
  Play,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
  Workflow,
  X,
} from 'lucide-react'
import {
  AgentApproval,
  AgentExecution,
  AgentExecutionStep,
  ReportMetadata,
  approveAgentAction,
  cancelAgentExecution,
  createAgentExecution,
  listAgentExecutions,
  listExecutionSteps,
  listPendingApprovals,
  listReports,
  rejectAgentAction,
  retryAgentExecution,
} from '@/src/api'
import { Badge, EmptyState, PageHeader, StatCard, StatusBadge, formatDate, timeAgo } from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

const SUGGESTIONS = [
  'Summarize all indexed vendor contracts and highlight renewal dates.',
  'Compare our security policy with the latest incident report.',
  'Find action items from recent project documentation.',
]

function resultText(result: Record<string, unknown> | null): string {
  if (!result) return ''
  if (typeof result.answer === 'string') return result.answer
  if (typeof result.summary === 'string') return result.summary
  return JSON.stringify(result, null, 2)
}

function ChartResult({ chart }: { chart: unknown }) {
  if (!chart || typeof chart !== 'object') return null
  const spec = chart as { type?: string; data?: { labels?: unknown[]; datasets?: Array<{ label?: string; data?: unknown[] }> } }
  const labels = Array.isArray(spec.data?.labels) ? spec.data.labels : []
  const values = Array.isArray(spec.data?.datasets?.[0]?.data) ? spec.data.datasets[0].data : []
  if (!labels.length || !values.length) return null
  const numeric = values.map((value) => typeof value === 'number' ? value : Number(value))
  const max = Math.max(1, ...numeric.filter((value) => Number.isFinite(value)))
  return (
    <div style={{ marginTop: 12 }}>
      <p className="nx-label" style={{ marginBottom: 8 }}>
        {spec.type === 'line' ? 'Trend' : 'Result chart'} � {spec.data?.datasets?.[0]?.label ?? 'value'}
      </p>
      <div className="nx-bars" style={{ height: 100 }}>
        {numeric.map((value, index) => (
          <span
            key={`${String(labels[index])}-${index}`}
            title={`${String(labels[index])}: ${Number.isFinite(value) ? value : 'not numeric'}`}
            style={{ height: `${Number.isFinite(value) ? Math.max(4, (value / max) * 100) : 4}%`, opacity: Number.isFinite(value) ? 0.85 : 0.25 }}
          />
        ))}
      </div>
      <div className="nx-row nx-row--between" style={{ marginTop: 7 }}>
        <span className="nx-xs nx-muted">{String(labels[0])}</span>
        <span className="nx-xs nx-muted">{String(labels[labels.length - 1])}</span>
      </div>
    </div>
  )
}

export default function AgentControlCenter() {
  const [request, setRequest] = useState('')
  const [executions, setExecutions] = useState<AgentExecution[]>([])
  const [steps, setSteps] = useState<Record<string, AgentExecutionStep[]>>({})
  const [approvals, setApprovals] = useState<AgentApproval[]>([])
  const [reports, setReports] = useState<ReportMetadata[]>([])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const loadedExecutions = await listAgentExecutions()
      setExecutions(loadedExecutions)
      const loadedSteps = await Promise.all(
        loadedExecutions.map(async (execution) => [execution.id, await listExecutionSteps(execution.id)] as const),
      )
      setSteps(Object.fromEntries(loadedSteps))
      const [loadedApprovals, loadedReports] = await Promise.all([listPendingApprovals(), listReports()])
      setApprovals(loadedApprovals)
      setReports(loadedReports)
      setError(null)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load agent executions')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const counts = useMemo(
    () => ({
      total: executions.length,
      succeeded: executions.filter((execution) => execution.status === 'succeeded').length,
      failed: executions.filter((execution) => execution.status === 'failed').length,
      approvals: approvals.length,
    }),
    [approvals.length, executions],
  )

  async function submit(event: React.FormEvent, preset?: string) {
    event.preventDefault()
    const value = (preset ?? request).trim()
    if (!value || running) return
    setRunning(true)
    setError(null)
    setMessage(null)
    try {
      const execution = await createAgentExecution(value)
      setExecutions((current) => [execution, ...current])
      setSteps((current) => ({ ...current, [execution.id]: [] }))
      setRequest('')
      setMessage('Execution submitted. Steps and results appear as they are persisted.')
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Agent execution failed')
    } finally {
      setRunning(false)
    }
  }

  async function cancelExecution(execution: AgentExecution) {
    if (!window.confirm('Cancel this execution and its pending steps?')) return
    setBusy(execution.id)
    setError(null)
    try {
      await cancelAgentExecution(execution.id)
      await refresh()
      setMessage('Execution cancelled and pending approvals revoked.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to cancel execution')
    } finally {
      setBusy(null)
    }
  }

  async function retryExecution(execution: AgentExecution) {
    setBusy(execution.id)
    setError(null)
    try {
      const updated = await retryAgentExecution(execution.id)
      setExecutions((current) => current.map((item) => item.id === updated.id ? updated : item))
      setMessage('Execution retried.')
      await refresh()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to retry execution')
    } finally {
      setBusy(null)
    }
  }

  async function decide(approval: AgentApproval, action: 'approve' | 'reject') {
    setBusy(approval.id)
    setError(null)
    try {
      if (action === 'approve') await approveAgentAction(approval.id)
      else {
        const reason = window.prompt('Rejection reason', 'Rejected by user')
        if (reason === null) return
        await rejectAgentAction(approval.id, reason || 'Rejected by user')
      }
      setApprovals((current) => current.filter((item) => item.id !== approval.id))
      setMessage(`${approval.action} ${action === 'approve' ? 'approved' : 'rejected'}.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to record decision')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Agent orchestration"
        title="Agent control center"
        description="Delegate multi-step work to the supervisor. Every step reuses the shared RAG pipeline and high-risk actions pause for explicit approval."
        actions={
          <>
            <Badge tone="violet" dot>supervisor</Badge>
            <Button variant="secondary" onClick={() => void refresh()} loading={loading}><RefreshCw size={14} /> Refresh</Button>
          </>
        }
      />

      <section className="nx-grid nx-grid--4">
        <StatCard icon={<Workflow />} label="Executions" value={counts.total} meta="Persisted runs" />
        <StatCard icon={<CheckCircle2 />} label="Succeeded" value={counts.succeeded} meta="Completed successfully" accent="green" progress={counts.total ? (counts.succeeded / counts.total) * 100 : 0} />
        <StatCard icon={<AlertTriangle />} label="Failed" value={counts.failed} meta="Requires review" accent="pink" />
        <StatCard icon={<ShieldAlert />} label="Approvals" value={counts.approvals} meta="Waiting for a human" accent="violet" />
      </section>

      <Card title="Run a supervised task" subtitle="Describe the outcome; the supervisor plans and delegates to specialists" glow="violet">
        <form onSubmit={submit} className="nx-stack" style={{ gap: 12 }}>
          <Input
            value={request}
            onChange={(event) => setRequest(event.target.value)}
            placeholder="Ask the supervisor to analyze permitted knowledge, generate a report, or coordinate an approval…"
            style={{ height: 46 }}
            disabled={running}
          />
          <div className="nx-row nx-row--between">
            <div className="nx-row" style={{ gap: 6 }}>
              {SUGGESTIONS.map((suggestion) => (
                <button key={suggestion} type="button" className="nx-badge" style={{ cursor: 'pointer', textTransform: 'none', letterSpacing: 0 }} onClick={() => setRequest(suggestion)}>
                  {suggestion.length > 46 ? `${suggestion.slice(0, 46)}…` : suggestion}
                </button>
              ))}
            </div>
            <Button type="submit" loading={running}><Play size={13} /> {running ? 'Running…' : 'Run supervisor'}</Button>
          </div>
        </form>
      </Card>

      {error && <div className="nx-error">{error}</div>}
      {message && <div className="nx-success">{message}</div>}

      <div className="nx-grid nx-grid--sidebar" style={{ alignItems: 'start' }}>
        <div className="nx-stack">
          <Card title="Execution history" subtitle={`${executions.length} persisted run${executions.length === 1 ? '' : 's'}`} flush>
            {loading ? (
              <div style={{ padding: '0 22px 22px' }} className="nx-stack">
                <div className="nx-skeleton" style={{ height: 70 }} />
                <div className="nx-skeleton" style={{ height: 70 }} />
              </div>
            ) : executions.length === 0 ? (
              <EmptyState icon={<Bot />} title="No executions yet" description="Run the supervisor above to create a persisted plan, steps and result." />
            ) : (
              <div style={{ padding: '0 22px 22px' }} className="nx-stack">
                {executions.map((execution) => (
                  <article key={execution.id} className="nx-card" style={{ padding: 16, boxShadow: 'none' }}>
                    <div className="nx-row nx-row--between" style={{ alignItems: 'flex-start' }}>
                      <div className="nx-row" style={{ alignItems: 'flex-start', gap: 10 }}>
                        <span className="nx-list-item__icon"><Bot /></span>
                        <div>
                          <p className="nx-small" style={{ margin: 0, fontWeight: 700, lineHeight: 1.45 }}>{execution.request}</p>
                          <p className="nx-xs nx-muted" style={{ margin: '4px 0 0' }}>{execution.agent_type} · {timeAgo(execution.created_at)} · {formatDate(execution.created_at)}</p>
                        </div>
                      </div>
                      <StatusBadge status={execution.status} />
                    </div>

                    {execution.error && <div className="nx-error" style={{ marginTop: 10 }}>{execution.error}</div>}

                    {Boolean(execution.result?.chart) && <ChartResult chart={execution.result?.chart} />}

                    {execution.result && (
                      <details className="nx-details" style={{ marginTop: 12 }}>
                        <summary>Result</summary>
                        <div><pre className="nx-code">{resultText(execution.result)}</pre></div>
                      </details>
                    )}

                    {execution.result?.format === 'markdown' && (
                      <Link to="/app/reports" className="nx-btn nx-btn--outline nx-btn--sm" style={{ marginTop: 10 }}>
                        <FileText size={12} /> Open generated report
                      </Link>
                    )}

                    {execution.plan && Object.keys(execution.plan).length > 0 && (
                      <details className="nx-details" style={{ marginTop: 8 }}>
                        <summary>Plan</summary>
                        <div><pre className="nx-code">{JSON.stringify(execution.plan, null, 2)}</pre></div>
                      </details>
                    )}

                    {(steps[execution.id]?.length ?? 0) > 0 && (
                      <details className="nx-details" style={{ marginTop: 8 }}>
                        <summary>Steps · {steps[execution.id].length}</summary>
                        <div>
                          <div className="nx-timeline">
                            {steps[execution.id].map((step) => (
                              <div key={step.id} className="nx-timeline__item">
                                <div className="nx-row nx-row--between">
                                  <p className="nx-xs" style={{ margin: 0, fontWeight: 700 }}>{step.agent_id} · {step.description}</p>
                                  <StatusBadge status={step.status} />
                                </div>
                                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>{step.step_key}{step.error ? ` · ${step.error}` : ''}</p>
                                {step.output_summary && (
                                  <details className="nx-details" style={{ marginTop: 6 }}>
                                    <summary>Step output</summary>
                                    <div><pre className="nx-code" style={{ maxHeight: 140 }}>{JSON.stringify(step.output_summary, null, 2)}</pre></div>
                                  </details>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      </details>
                    )}

                    <div className="nx-row nx-row--between" style={{ marginTop: 10, gap: 8 }}>
                      <div className="nx-row" style={{ gap: 6 }}>
                        <Badge>{execution.id.slice(0, 8)}</Badge>
                        {execution.finished_at && <Badge tone="success">finished {timeAgo(execution.finished_at)}</Badge>}
                        {Boolean(execution.result?.citations) && <Badge tone="info">citations present</Badge>}
                      </div>
                      <div className="nx-row" style={{ gap: 6 }}>
                        {['queued', 'running', 'waiting_for_approval'].includes(execution.status) && (
                          <Button size="sm" variant="outline" onClick={() => void cancelExecution(execution)} loading={busy === execution.id}>
                            <X size={12} /> Cancel
                          </Button>
                        )}
                        {execution.status === 'failed' && (
                          <Button size="sm" variant="outline" onClick={() => void retryExecution(execution)} loading={busy === execution.id}>
                            <RotateCcw size={12} /> Retry
                          </Button>
                        )}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div className="nx-stack">
          <Card title="Pending approvals" subtitle="High-risk actions require a human decision" actions={<Badge tone={approvals.length ? 'warning' : 'success'}>{approvals.length} pending</Badge>}>
            {loading ? (
              <div className="nx-skeleton" style={{ height: 70 }} />
            ) : approvals.length === 0 ? (
              <EmptyState icon={<ShieldAlert />} title="No approvals waiting" description="Approval requests appear here when an agent requests a high-risk action." />
            ) : (
              <div className="nx-stack" style={{ gap: 9 }}>
                {approvals.map((approval) => (
                  <div key={approval.id} className="nx-card" style={{ padding: 14, boxShadow: 'none' }}>
                    <div className="nx-row nx-row--between">
                      <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>{approval.action}</p>
                      <Badge tone={approval.risk_level === 'high' ? 'danger' : 'warning'}>{approval.risk_level}</Badge>
                    </div>
                    <p className="nx-xs nx-muted" style={{ margin: '5px 0 0', lineHeight: 1.5 }}>{approval.action_summary}</p>
                    <p className="nx-xs nx-muted" style={{ margin: '5px 0 0' }}>{approval.agent_id} · requested {timeAgo(approval.requested_at)}</p>
                    <div className="nx-row" style={{ marginTop: 10, gap: 7 }}>
                      <Button size="sm" onClick={() => void decide(approval, 'approve')} loading={busy === approval.id}><ThumbsUp size={12} /> Approve</Button>
                      <Button size="sm" variant="outline" onClick={() => void decide(approval, 'reject')} loading={busy === approval.id}><ThumbsDown size={12} /> Reject</Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Generated reports" subtitle="Persisted report artifacts" actions={<FileText size={15} className="nx-muted" />}>
            {reports.length === 0 ? (
              <EmptyState icon={<FileText />} title="No reports yet" description="Reports generated by agents will appear here with their real file format and timestamp." />
            ) : (
              <div className="nx-list">
                {reports.map((report) => (
                  <div key={report.id} className="nx-list-item">
                    <span className="nx-list-item__icon"><FileText /></span>
                    <div className="nx-list-item__body">
                      <p className="nx-list-item__title">{report.title}</p>
                      <p className="nx-list-item__sub">{report.report_type} · {report.file_format} · {formatDate(report.created_at)}</p>
                    </div>
                    <StatusBadge status={report.status} />
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
