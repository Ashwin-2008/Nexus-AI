import React from 'react'
import { Card } from '@/components/ui'
import { health, listDocuments } from '@/src/api'

export default function Dashboard() {
  const [documents, setDocuments] = React.useState<number | null>(null)
  const [status, setStatus] = React.useState<string>('unavailable')
  React.useEffect(() => {
    listDocuments().then((items) => setDocuments(items.length)).catch(() => setDocuments(null))
    health().then((result) => setStatus(result.status)).catch(() => setStatus('unavailable'))
  }, [])
  return (
    <div className="space-y-6">
      <Card title="Overview">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="group bg-card border border-border rounded-lg p-6 hover:shadow-sm transition-shadow">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Data Sources</span>
              <span className="text-2xl font-bold text-gray-900">Unavailable</span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">Connected sources</p>
          </div>
          <div className="group bg-card border border-border rounded-lg p-6 hover:shadow-sm transition-shadow">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Documents</span>
              <span className="text-2xl font-bold text-gray-900">{documents ?? 'Unavailable'}</span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">Indexed documents</p>
          </div>
          <div className="group bg-card border border-border rounded-lg p-6 hover:shadow-sm transition-shadow">
            <div className="flex items-center justify-between">
              <span className="text-sm text-muted-foreground">Active Jobs</span>
              <span className="text-2xl font-bold text-gray-900">Unavailable</span>
            </div>
            <p className="mt-2 text-sm text-muted-foreground">Ingestion jobs</p>
          </div>
        </div>
      </Card>

      <Card title="System Status">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="flex items-start gap-3">
            <div className="w-3 h-3 rounded-full bg-green-500 flex-shrink-0"></div>
            <div>
              <p className="text-sm text-muted-foreground">Backend</p>
              <p className="text-xs font-medium">{status}</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-3 h-3 rounded-full bg-yellow-500 flex-shrink-0"></div>
            <div>
              <p className="text-sm text-muted-foreground">Vector Search</p>
              <p className="text-xs font-medium text-muted-foreground">Unavailable</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <div className="w-3 h-3 rounded-full bg-red-500 flex-shrink-0"></div>
            <div>
              <p className="text-sm text-muted-foreground">Redis</p>
              <p className="text-xs font-medium text-muted-foreground">Unavailable</p>
            </div>
          </div>
        </div>
      </Card>

      <Card title="Recent Activity">
        <div className="space-y-4">
          <div className="flex items-center justify-between pb-2 border-b last:border-0">
            <span className="text-sm text-muted-foreground">Last 24 hours</span>
            <a href="#" className="text-xs text-primary underline">
              View all
            </a>
          </div>
          <p className="text-sm text-muted-foreground">Recent activity is unavailable because no activity endpoint exists.</p>
        </div>
      </Card>
    </div>
  )
}