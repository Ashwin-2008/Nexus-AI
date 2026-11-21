import React, { useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  Database,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Table2,
  Wand2,
} from 'lucide-react'
import {
  AgentExecution,
  DataSource,
  DatabaseSchema,
  createAgentExecution,
  databaseSchema,
  generateSql,
  listSources,
  validateSql,
} from '@/src/api'
import { Badge, EmptyState, Field, PageHeader, StatCard, StatusBadge, formatNumber } from '@/components/nx'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Input, Select, Textarea } from '@/components/ui/input'

interface QueryResult {
  driver?: string
  columns?: string[]
  rows?: unknown[][]
  row_count?: number
  truncated?: boolean
}

interface ChartSpec {
  type?: string
  data?: { labels?: unknown[]; datasets?: Array<{ label?: string; data?: unknown[] }> }
}

function resultDatabase(execution: AgentExecution | null): QueryResult | null {
  const value = execution?.result?.database
  return value && typeof value === 'object' ? value as QueryResult : null
}

function resultChart(execution: AgentExecution | null): ChartSpec | null {
  const analytics = execution?.result?.analytics
  if (!analytics || typeof analytics !== 'object') return null
  const value = (analytics as Record<string, unknown>).chart
  return value && typeof value === 'object' ? value as ChartSpec : null
}

export default function DatabaseIntelligence() {
  const [sources, setSources] = useState<DataSource[]>([])
  const [sourceId, setSourceId] = useState('')
  const [schema, setSchema] = useState<DatabaseSchema | null>(null)
  const [question, setQuestion] = useState('')
  const [sql, setSql] = useState('')
  const [maxRows, setMaxRows] = useState(100)
  const [execution, setExecution] = useState<AgentExecution | null>(null)
  const [loadingSources, setLoadingSources] = useState(true)
  const [schemaLoading, setSchemaLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [validating, setValidating] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    listSources()
      .then((all) => {
        const databases = all.filter((source) => source.type === 'postgres' || source.type === 'mysql')
        setSources(databases)
        setSourceId((current) => current || databases[0]?.id || '')
      })
      .catch((caught) => setError(caught instanceof Error ? caught.message : 'Unable to load database sources'))
      .finally(() => setLoadingSources(false))
  }, [])

  const database = resultDatabase(execution)
  const chart = resultChart(execution)

  const tableCount = schema?.tables.length ?? 0
  const columnCount = useMemo(
    () => schema?.tables.reduce((total, table) => total + table.columns.length, 0) ?? 0,
    [schema],
  )

  async function discover() {
    if (!sourceId) return
    setSchemaLoading(true)
    setError(null)
    setMessage(null)
    try {
      setSchema(await databaseSchema(sourceId))
    } catch (caught) {
      setSchema(null)
      setError(caught instanceof Error ? caught.message : 'Schema discovery failed')
    } finally {
      setSchemaLoading(false)
    }
  }

  async function generate() {
    if (!sourceId || !question.trim()) return
    setGenerating(true)
    setError(null)
    setMessage(null)
    try {
      const result = await generateSql(sourceId, question.trim())
      setSql(result.sql)
      setSchema(result.schema)
      setMessage('SQL generated and validated as read-only. Review it before execution.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'SQL generation failed')
    } finally {
      setGenerating(false)
    }
  }

  async function validate() {
    if (!sql.trim()) return
    setValidating(true)
    setError(null)
    setMessage(null)
    try {
      const result = await validateSql(sql, maxRows)
      setSql(result.sql)
      setMessage('Query is read-only and within the row bound.')
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'SQL validation failed')
    } finally {
      setValidating(false)
    }
  }

  async function run() {
    if (!sourceId || !sql.trim()) return
    setRunning(true)
    setError(null)
    setMessage(null)
    setExecution(null)
    try {
      const result = await createAgentExecution(question.trim() || 'Execute a validated read-only query', sourceId, sql, maxRows)
      setExecution(result)
      if (result.status === 'failed') setError(result.error || 'Query execution failed')
      else setMessage(`Query completed with ${formatNumber(resultDatabase(result)?.row_count ?? 0)} result rows.`)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Query execution failed')
    } finally {
      setRunning(false)
    }
  }

  return (
    <div className="nx-stack" style={{ gap: 22 }}>
      <PageHeader
        eyebrow="Database intelligence"
        title="Database"
        description="Discover permitted schemas, generate or validate read-only SQL, execute it through the safe SQL boundary and inspect measured results and chart specs."
        actions={
          <>
            <Button variant="secondary" onClick={() => void discover()} loading={schemaLoading} disabled={!sourceId}><RefreshCw size={14} /> Discover schema</Button>
            <Button onClick={() => void run()} loading={running} disabled={!sql.trim()}><Play size={14} /> Run query</Button>
          </>
        }
      />

      <section className="nx-grid nx-grid--4">
        <StatCard icon={<Database />} label="Database sources" value={sources.length} meta="PostgreSQL / MySQL connectors" />
        <StatCard icon={<Table2 />} label="Tables" value={schema ? formatNumber(tableCount) : '—'} meta={schema ? `${formatNumber(columnCount)} columns discovered` : 'Discover a schema'} accent="violet" />
        <StatCard icon={<CheckCircle2 />} label="Rows returned" value={database ? formatNumber(database.row_count ?? 0) : '—'} meta={database?.truncated ? 'Result was bounded' : 'Last execution'} accent="green" />
        <StatCard icon={<ShieldCheck />} label="Safety" value="read-only" meta="SELECT / WITH only" accent="pink" />
      </section>

      {error && <div className="nx-error">{error}</div>}
      {message && <div className="nx-success">{message}</div>}

      {loadingSources ? (
        <div className="nx-skeleton" style={{ height: 110 }} />
      ) : sources.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Database />}
            title="No database source configured"
            description="Connect a PostgreSQL or MySQL source in Sources with a read-only account. The password belongs in encrypted credentials, not config."
          />
        </Card>
      ) : (
        <div className="nx-grid nx-grid--sidebar" style={{ alignItems: 'start' }}>
          <div className="nx-stack">
            <Card title="Ask in natural language" subtitle="Uses the configured LLM when available, then validates the output" glow="violet">
              <div className="nx-stack" style={{ gap: 12 }}>
                <div className="nx-grid nx-grid--2" style={{ gap: 10 }}>
                  <Field label="Database source">
                    <Select value={sourceId} onChange={(event) => { setSourceId(event.target.value); setSchema(null); setExecution(null) }}>
                      {sources.map((source) => <option key={source.id} value={source.id}>{source.name} · {source.type}</option>)}
                    </Select>
                  </Field>
                  <Field label="Row limit">
                    <Select value={maxRows} onChange={(event) => setMaxRows(Number(event.target.value))}>
                      {[25, 50, 100, 500, 1000].map((value) => <option key={value} value={value}>{value} rows</option>)}
                    </Select>
                  </Field>
                </div>
                <Field label="Question">
                  <Input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Which accounts renewed last quarter, grouped by region?" />
                </Field>
                <div className="nx-row nx-row--between">
                  <span className="nx-xs nx-muted">Generated SQL is re-validated server-side before execution. Comments, multiple statements and mutations are rejected.</span>
                  <Button onClick={() => void generate()} loading={generating} disabled={!question.trim()}><Wand2 size={13} /> Generate SQL</Button>
                </div>
              </div>
            </Card>

            <Card
              title="Read-only SQL"
              subtitle="Review, validate and execute through the safe SQL boundary"
              actions={<Badge tone="info"><ShieldCheck size={10} /> bounded</Badge>}
            >
              <div className="nx-stack" style={{ gap: 12 }}>
                <Textarea
                  value={sql}
                  onChange={(event) => setSql(event.target.value)}
                  placeholder="SELECT id, name, renewal_date FROM accounts WHERE renewal_date >= '2026-01-01'"
                  spellCheck={false}
                  style={{ minHeight: 170, fontFamily: 'monospace', fontSize: 11.5 }}
                />
                <div className="nx-row nx-row--between">
                  <div className="nx-row" style={{ gap: 6 }}>
                    <Badge tone="violet">SELECT / WITH</Badge>
                    <Badge>max {maxRows} rows</Badge>
                  </div>
                  <div className="nx-row" style={{ gap: 8 }}>
                    <Button variant="outline" onClick={() => void validate()} loading={validating} disabled={!sql.trim()}>Validate</Button>
                    <Button onClick={() => void run()} loading={running} disabled={!sql.trim()}><Play size={13} /> Execute</Button>
                  </div>
                </div>
                {execution && (
                  <div className="nx-row" style={{ gap: 8 }}>
                    <StatusBadge status={execution.status} />
                    <Badge>{execution.id.slice(0, 8)}</Badge>
                    {execution.finished_at && <Badge tone="success">finished</Badge>}
                  </div>
                )}
              </div>
            </Card>

            {database && (
              <Card
                title="Result set"
                subtitle={`${database.driver ?? 'database'} · ${formatNumber(database.row_count ?? 0)} rows${database.truncated ? ' · bounded' : ''}`}
                flush
              >
                {(database.rows?.length ?? 0) === 0 ? (
                  <EmptyState icon={<Table2 />} title="No rows returned" description="The query executed successfully but returned no records." />
                ) : (
                  <div className="nx-table__wrap" style={{ border: 0, borderRadius: 0, background: 'transparent', maxHeight: 420 }}>
                    <table className="nx-table">
                      <thead><tr>{(database.columns ?? []).map((column) => <th key={column}>{column}</th>)}</tr></thead>
                      <tbody>
                        {(database.rows ?? []).map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {row.map((value, columnIndex) => (
                              <td key={columnIndex} className="nx-xs">{value === null || value === undefined ? '—' : String(value)}</td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            )}

            {chart?.data?.labels?.length && chart.data.datasets?.[0]?.data?.length ? (
              <Card title="Result chart" subtitle="Measured from the returned result set">
                {(() => {
                  const values = (chart.data.datasets?.[0]?.data ?? []).map((value) => typeof value === 'number' ? value : Number(value))
                  const max = Math.max(1, ...values.filter((value) => Number.isFinite(value)))
                  return (
                    <>
                      <div className="nx-bars" style={{ height: 110 }}>
                        {values.map((value, index) => (
                          <span key={index} title={`${String(chart.data?.labels?.[index])}: ${Number.isFinite(value) ? value : 'not numeric'}`} style={{ height: `${Number.isFinite(value) ? Math.max(4, (value / max) * 100) : 4}%`, opacity: Number.isFinite(value) ? 0.85 : 0.25 }} />
                        ))}
                      </div>
                      <div className="nx-row nx-row--between" style={{ marginTop: 7 }}>
                        <span className="nx-xs nx-muted">{String(chart.data.labels[0])}</span>
                        <span className="nx-xs nx-muted">{String(chart.data.labels[chart.data.labels.length - 1])}</span>
                      </div>
                    </>
                  )
                })()}
              </Card>
            ) : null}
          </div>

          <div className="nx-stack">
            <Card title="Schema explorer" subtitle={schema ? `${formatNumber(tableCount)} tables · ${formatNumber(columnCount)} columns` : 'Discover the permitted schema'} actions={<Table2 size={15} className="nx-muted" />}>
              {schemaLoading ? (
                <div className="nx-skeleton" style={{ height: 90 }} />
              ) : !schema ? (
                <EmptyState icon={<Sparkles />} title="No schema loaded" description="Discover the schema to inspect table and column metadata before writing SQL." action={<Button size="sm" onClick={() => void discover()}>Discover schema</Button>} />
              ) : schema.tables.length === 0 ? (
                <EmptyState icon={<AlertTriangle />} title="No tables discovered" description="The configured account may not have access to any tables." />
              ) : (
                <div className="nx-stack" style={{ gap: 7 }}>
                  {schema.tables.map((table) => (
                    <details key={`${table.schema}.${table.table}`} className="nx-details">
                      <summary>{table.schema}.{table.table} · {table.columns.length} cols</summary>
                      <div>
                        <div className="nx-table__wrap">
                          <table className="nx-table">
                            <thead><tr><th>Column</th><th>Type</th><th>Nullable</th></tr></thead>
                            <tbody>
                              {table.columns.map((column) => (
                                <tr key={column.name}>
                                  <td className="nx-xs nx-mono">{column.name}{table.primary_key.includes(column.name) ? ' · PK' : ''}</td>
                                  <td className="nx-xs">{column.type}</td>
                                  <td className="nx-xs">{column.nullable ? 'yes' : 'no'}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    </details>
                  ))}
                </div>
              )}
              {schema?.truncated && <div className="nx-error" style={{ marginTop: 10 }}>Schema listing was truncated at the configured table limit.</div>}
            </Card>

            <Card title="Safety boundary" subtitle="Enforced server-side, not only in this UI">
              <div className="nx-timeline">
                <div className="nx-timeline__item"><p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Read-only statement</p><p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>Only SELECT and WITH statements pass validation; mutations, comments and stacked statements are rejected.</p></div>
                <div className="nx-timeline__item"><p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Bounded rows</p><p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>Queries without LIMIT are wrapped and capped at the requested row limit.</p></div>
                <div className="nx-timeline__item"><p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>Encrypted credentials</p><p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>SQL passwords are injected from encrypted credentials; config stays secret-free.</p></div>
                <div className="nx-timeline__item"><p className="nx-small" style={{ margin: 0, fontWeight: 700 }}>No invented metrics</p><p className="nx-xs nx-muted" style={{ margin: '3px 0 0', lineHeight: 1.55 }}>Tables and charts render values returned by the database, not generated estimates.</p></div>
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}
