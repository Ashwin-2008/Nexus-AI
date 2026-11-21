import React from 'react'
import { Card, Button, Input } from '@/components/ui'
import {
  AgentApproval,
  AgentExecution,
  AgentExecutionStep,
  approveAgentAction,
  createAgentExecution,
  listAgentExecutions,
  listExecutionSteps,
  listPendingApprovals,
  rejectAgentAction,
  listReports,
  ReportMetadata,
} from '@/src/api'

export default function AgentControlCenter() {
  const [request, setRequest] = React.useState('')
  const [executions, setExecutions] = React.useState<AgentExecution[]>([])
  const [loading, setLoading] = React.useState(true)
  const [running, setRunning] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)
  const [steps, setSteps] = React.useState<Record<string, AgentExecutionStep[]>>({})
  const [approvals, setApprovals] = React.useState<AgentApproval[]>([])
  const [reports, setReports] = React.useState<ReportMetadata[]>([])

  const refresh = React.useCallback(async () => {
    try {
      const loadedExecutions = await listAgentExecutions()
      setExecutions(loadedExecutions)
      const loadedSteps = await Promise.all(loadedExecutions.map(async (execution) => [execution.id, await listExecutionSteps(execution.id)] as const))
      setSteps(Object.fromEntries(loadedSteps))
      setApprovals(await listPendingApprovals())
      setReports(await listReports())
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unable to load agent executions')
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => { void refresh() }, [refresh])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!request.trim()) return
    setRunning(true)
    setError(null)
    try {
      const execution = await createAgentExecution(request.trim())
      setExecutions((current) => [execution, ...current])
      const executionSteps = await listExecutionSteps(execution.id)
      setSteps((current) => ({ ...current, [execution.id]: executionSteps }))
      setRequest('')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Agent execution failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className='space-y-6'>
      <Card title='Agent control center'>
        <form className='flex gap-3' onSubmit={submit}>
          <Input className='flex-1' placeholder='Ask the supervisor to analyze permitted knowledge...' value={request} onChange={(e) => setRequest(e.target.value)} />
          <Button type='submit' disabled={running}>{running ? 'Running...' : 'Run'}</Button>
        </form>
        <p className='mt-2 text-xs text-muted-foreground'>Executions use organization-scoped retrieval and persist their plan, result, and status.</p>
      </Card>

      <Card title='Execution history'>
        {loading && <p className='text-muted-foreground'>Loading executions...</p>}
        {!loading && executions.length === 0 && <p className='text-muted-foreground'>No executions yet.</p>}
        <div className='space-y-3'>
          {executions.map((execution) => (
            <article key={execution.id} className='rounded-md border border-border p-4'>
              <div className='flex flex-wrap justify-between gap-2'>
                <p className='font-medium'>{execution.request}</p>
                <span className='text-sm text-muted-foreground'>{execution.agent_type} · {execution.status}</span>
              </div>
              {execution.error && <p className='mt-2 text-sm text-red-600'>{execution.error}</p>}
              {execution.result && <pre className='mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-muted p-3 text-xs'>{JSON.stringify(execution.result, null, 2)}</pre>}
              <div className='mt-3 space-y-1'>
                {(steps[execution.id] ?? []).map((step) => <p key={step.id} className='text-xs text-muted-foreground'>{step.agent_id} · {step.status} · {step.description}</p>)}
              </div>
              <p className='mt-2 text-xs text-muted-foreground'>{new Date(execution.created_at).toLocaleString()}</p>
            </article>
          ))}
        </div>
      </Card>
      <Card title='Pending approvals'>
        {approvals.length === 0 ? <p className='text-muted-foreground'>No approval requests.</p> : approvals.map((approval) => (
          <div key={approval.id} className='mb-3 rounded-md border border-border p-3'>
            <p className='font-medium'>{approval.action}</p>
            <p className='text-sm text-muted-foreground'>{approval.action_summary}</p>
            {approval.expires_at && <p className='text-xs text-muted-foreground'>Expires {new Date(approval.expires_at).toLocaleString()}</p>}
            <div className='mt-2 flex gap-2'>
              <Button size='sm' onClick={async () => { await approveAgentAction(approval.id); setApprovals((current) => current.filter((item) => item.id !== approval.id)) }}>Approve</Button>
              <Button size='sm' variant='outline' onClick={async () => { await rejectAgentAction(approval.id, 'Rejected by user'); setApprovals((current) => current.filter((item) => item.id !== approval.id)) }}>Reject</Button>
            </div>
          </div>
        ))}
      </Card>
      <Card title='Generated reports'>
        {reports.length === 0 ? <p className='text-muted-foreground'>No reports generated yet.</p> : reports.map((report) => (
          <div key={report.id} className='mb-3 flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3'>
            <div><p className='font-medium'>{report.title}</p><p className='text-xs text-muted-foreground'>{report.report_type} · {report.file_format} · {new Date(report.created_at).toLocaleString()}</p></div>
            {report.storage_key && <a className='text-sm underline' href={`/api/v1/intelligence/reports/${encodeURIComponent(report.storage_key.split('/').pop()?.split('.')[0] ?? '')}?format=${report.file_format}`}>Download</a>}
          </div>
        ))}
      </Card>
      {error && <p className='text-sm text-red-600'>{error}</p>}
    </div>
  )
}
