import React, { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  Bot,
  Building2,
  Cpu,
  Database,
  FileStack,
  KeyRound,
  Layers,
  RefreshCw,
  ScrollText,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Users,
  Workflow,
} from 'lucide-react'
import { useAuth } from '@/src/auth'
import { AdminOverview, AdminUser, AgentCatalogItem, AuditLogEntry, SystemCapabilities, adminAuditLogs, adminOverview, adminUsers, agentCatalog, systemCapabilities } from '@/src/api'
import { Badge, EmptyState, PageHeader, StatCard, StatusBadge, formatDate, formatNumber, timeAgo } from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'

const COUNT_LABELS: Array<{ key: string; label: string; icon: React.ReactNode }> = [
  { key: 'users', label: 'Users', icon: <Users /> },
  { key: 'active_users', label: 'Active users', icon: <ShieldCheck /> },
  { key: 'documents', label: 'Documents', icon: <FileStack /> },
  { key: 'chunks', label: 'Chunks', icon: <Layers /> },
  { key: 'sources', label: 'Sources', icon: <Database /> },
  { key: 'agent_executions', label: 'Agent runs', icon: <Bot /> },
  { key: 'rag_queries', label: 'RAG queries', icon: <Sparkles /> },
  { key: 'reports', label: 'Reports', icon: <ScrollText /> },
]

export default function Administration() {
  const { user } = useAuth()
  const [overview, setOverview] = useState<AdminOverview | null>(null)
  const [users, setUsers] = useState<AdminUser[]>([])
  const [logs, setLogs] = useState<AuditLogEntry[]>([])
  const [capabilities, setCapabilities] = useState<SystemCapabilities | null>(null)
  const [catalog, setCatalog] = useState<AgentCatalogItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const isAdmin = user?.role === 'admin'

  async function load() {
    if (!isAdmin) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [overviewResult, usersResult, logsResult, capabilityResult, catalogResult] = await Promise.all([
        adminOverview(),
        adminUsers(200, 0),
        adminAuditLogs(100),
        systemCapabilities(),
        agentCatalog(),
      ])
      setOverview(overviewResult)
      setUsers(usersResult.items)
      setLogs(logsResult.items)
      setCapabilities(capabilityResult)
      setCatalog(catalogResult)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to load administration data')
      setOverview(null)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin])

  const roleCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const member of users) {
      const role = member.role ?? 'unknown'
      counts[role] = (counts[role] ?? 0) + 1
    }
    return counts
  }, [users])

  if (!isAdmin) {
    return (
      <div className="nx-stack" style={{ gap: 22 }}>
        <PageHeader eyebrow="Organization" title="Administration" description="Organization-wide visibility is restricted to administrators." />
        <Card>
          <EmptyState
            icon={<ShieldAlert />}
            title="Administrator role required"
            description="Your account is a member of this organization. Ask an administrator to grant the admin role if you need organization-wide visibility."
          />
        </Card>
      </div>
    )
  }

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Organization"
        title="Administration"
        description="Read-only organization visibility across members, knowledge, agents, telemetry and audit history."
        actions={
          <>
            <Badge tone="violet"><ShieldCheck size={10} /> admin</Badge>
            <Button variant="secondary" onClick={() => void load()} loading={loading}><RefreshCw size={14} /> Refresh</Button>
          </>
        }
      />

      {error && <div className="nx-error">{error}</div>}

      <section className="nx-grid nx-grid--sidebar" style={{ alignItems: 'start' }}>
        <div className="nx-stack">
          <Card title="Organization" subtitle="Isolated tenant boundary for every record" glow="violet">
            <div className="nx-row" style={{ gap: 14 }}>
              <span className="nx-logo-mark" style={{ width: 52, height: 52, transform: 'none' }}><Building2 size={22} /></span>
              <div>
                <p style={{ margin: 0, fontSize: 18, fontWeight: 800 }}>{overview?.organization.name ?? user?.email}</p>
                <p className="nx-xs nx-muted nx-mono" style={{ margin: '4px 0 0' }}>{overview?.organization.id ?? user?.organization_id}</p>
                <div className="nx-row" style={{ marginTop: 7, gap: 6 }}>
                  <Badge tone="success" dot>active</Badge>
                  <Badge tone="info">{overview?.role ?? user?.role}</Badge>
                </div>
              </div>
            </div>
            <div className="nx-divider" />
            <div className="nx-grid nx-grid--3" style={{ gap: 10 }}>
              <div>
                <p className="nx-xs nx-muted" style={{ margin: 0 }}>Members</p>
                <p style={{ margin: '4px 0 0', fontSize: 21, fontWeight: 800 }}>{formatNumber(overview?.counts.users ?? users.length)}</p>
              </div>
              <div>
                <p className="nx-xs nx-muted" style={{ margin: 0 }}>Documents</p>
                <p style={{ margin: '4px 0 0', fontSize: 21, fontWeight: 800 }}>{formatNumber(overview?.counts.documents ?? 0)}</p>
              </div>
              <div>
                <p className="nx-xs nx-muted" style={{ margin: 0 }}>Chunks</p>
                <p style={{ margin: '4px 0 0', fontSize: 21, fontWeight: 800 }}>{formatNumber(overview?.counts.chunks ?? 0)}</p>
              </div>
            </div>
          </Card>

          <section className="nx-grid nx-grid--4">
            {COUNT_LABELS.map((item, index) => (
              <StatCard
                key={item.key}
                icon={item.icon}
                label={item.label}
                value={loading ? 'â€”' : formatNumber(overview?.counts[item.key] ?? 0)}
                meta={index < 2 ? 'Organization members' : 'Persisted records'}
                accent={index % 4 === 0 ? 'cyan' : index % 4 === 1 ? 'violet' : index % 4 === 2 ? 'pink' : 'green'}
              />
            ))}
          </section>

          <Card title="Members" subtitle={`${users.length} user${users.length === 1 ? '' : 's'} in this organization`} flush>
            {loading ? (
              <div style={{ padding: '0 22px 22px' }}><div className="nx-skeleton" style={{ height: 100 }} /></div>
            ) : users.length === 0 ? (
              <EmptyState icon={<Users />} title="No members" description="Organization membership is empty." />
            ) : (
              <div className="nx-table__wrap" style={{ border: 0, borderRadius: 0, background: 'transparent' }}>
                <table className="nx-table">
                  <thead><tr><th>Member</th><th>Email</th><th>Role</th><th>Status</th><th>Joined</th></tr></thead>
                  <tbody>
                    {users.map((member) => (
                      <tr key={member.id}>
                        <td>
                          <span className="nx-row" style={{ gap: 9 }}>
                            <span className="nx-avatar" style={{ width: 30, height: 30, borderRadius: 9, fontSize: 10 }}>{(member.full_name || member.email).slice(0, 2).toUpperCase()}</span>
                            <span className="nx-small" style={{ fontWeight: 700 }}>{member.full_name || 'Unnamed member'}</span>
                          </span>
                        </td>
                        <td className="nx-xs">{member.email}</td>
                        <td><Badge tone={member.role === 'admin' ? 'violet' : 'info'}>{member.role ?? 'member'}</Badge></td>
                        <td><StatusBadge status={member.is_active ? 'active' : 'disabled'} /></td>
                        <td className="nx-xs nx-muted">{formatDate(member.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Audit history" subtitle="Most recent organization events" flush>
            {loading ? (
              <div style={{ padding: '0 22px 22px' }}><div className="nx-skeleton" style={{ height: 100 }} /></div>
            ) : logs.length === 0 ? (
              <EmptyState icon={<ScrollText />} title="No audit entries" description="Audited actions appear here as they occur." />
            ) : (
              <div style={{ padding: '0 22px 22px' }}>
                <div className="nx-timeline">
                  {logs.map((log) => (
                    <div key={log.id} className="nx-timeline__item">
                      <div className="nx-row nx-row--between" style={{ alignItems: 'flex-start' }}>
                        <div>
                          <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>{log.action}</p>
                          <p className="nx-xs nx-muted" style={{ margin: '3px 0 0' }}>
                            {log.resource_type || 'resource'}{log.resource_id ? ` Â· ${log.resource_id.slice(0, 12)}â€¦` : ''}
                          </p>
                          {log.details && <pre className="nx-code" style={{ marginTop: 6, maxHeight: 100 }}>{log.details}</pre>}
                        </div>
                        <span className="nx-xs nx-muted nx-nowrap">{timeAgo(log.created_at)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>

        <div className="nx-stack">
          <Card title="AI providers" subtitle="Resolved runtime configuration" actions={<Cpu size={15} className="nx-muted" />}>
            {capabilities ? (
              <div className="nx-stack" style={{ gap: 9 }}>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">LLM</span><Badge tone={capabilities.providers.llm.available ? 'success' : 'warning'}>{capabilities.providers.llm.provider}</Badge></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Model</span><span className="nx-xs nx-mono">{capabilities.providers.llm.model}</span></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Embeddings</span><Badge tone={capabilities.providers.embeddings.semantic ? 'success' : 'warning'}>{capabilities.providers.embeddings.provider}</Badge></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Vector</span><Badge tone="violet">{capabilities.providers.vector.backend}</Badge></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Storage</span><Badge>{capabilities.providers.storage.backend}</Badge></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Reranker</span><Badge tone="info">{String(capabilities.retrieval.reranker ?? '—')}</Badge></div>
                <div className="nx-row nx-row--between"><span className="nx-xs nx-muted">Celery</span><Badge tone={capabilities.worker.celery_enabled ? 'success' : 'warning'}>{capabilities.worker.celery_enabled ? 'enabled' : 'in-process'}</Badge></div>
              </div>
            ) : <p className="nx-xs nx-muted" style={{ margin: 0 }}>Provider configuration unavailable.</p>}
          </Card>

          <Card title="Agent catalog" subtitle={`${catalog.length} registered specialists`} actions={<Workflow size={15} className="nx-muted" />}>
            {catalog.length === 0 ? (
              <p className="nx-xs nx-muted" style={{ margin: 0 }}>No agents registered.</p>
            ) : (
              <div className="nx-list">
                {catalog.map((agent) => (
                  <details key={agent.id} className="nx-details">
                    <summary>{agent.name} · {agent.id}</summary>
                    <div>
                      <p className="nx-xs nx-muted" style={{ margin: '0 0 7px', lineHeight: 1.55 }}>{agent.description}</p>
                      <div className="nx-row" style={{ gap: 5, flexWrap: 'wrap' }}>
                        {agent.capabilities.slice(0, 4).map((capability) => <Badge key={capability}>{capability}</Badge>)}
                        {agent.tools.slice(0, 3).map((tool) => <Badge key={tool} tone="violet">{tool}</Badge>)}
                      </div>
                    </div>
                  </details>
                ))}
              </div>
            )}
          </Card>

          <Card title="Roles" subtitle="Observed organization membership">
            {Object.keys(roleCounts).length === 0 ? <p className="nx-xs nx-muted" style={{ margin: 0 }}>No members loaded.</p> : (
              <div className="nx-hbar">
                {Object.entries(roleCounts).map(([role, count]) => (
                  <div key={role} className="nx-hbar__row">
                    <span style={{ textTransform: 'capitalize' }}>{role}</span>
                    <span className="nx-hbar__track"><span className="nx-hbar__fill" style={{ width: `${Math.round((count / Math.max(1, users.length)) * 100)}%` }} /></span>
                    <span className="nx-hbar__value">{count}</span>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Administration policy" subtitle="What this surface does">
            <div className="nx-timeline">
              <div className="nx-timeline__item">
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Read-only by design</p>
                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>This console exposes organization truth without inventing mutation endpoints.</p>
              </div>
              <div className="nx-timeline__item">
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Server-enforced admin gate</p>
                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>The API rejects non-admin requests with 403 even if the route is called directly.</p>
              </div>
              <div className="nx-timeline__item">
                <p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Secrets never returned</p>
                <p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>Connector credentials and user password hashes are not part of these responses.</p>
              </div>
            </div>
          </Card>

          <Card title="Session" subtitle="Your administrator identity">
            <div className="nx-list">
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><KeyRound /></span>
                <div className="nx-list-item__body"><p className="nx-list-item__title">Role</p><p className="nx-list-item__sub">{user?.role}</p></div>
              </div>
              <div className="nx-list-item">
                <span className="nx-list-item__icon"><Activity /></span>
                <div className="nx-list-item__body"><p className="nx-list-item__title">User</p><p className="nx-list-item__sub">{user?.email}</p></div>
              </div>
            </div>
          </Card>
        </div>
      </section>
    </div>
  )
}
