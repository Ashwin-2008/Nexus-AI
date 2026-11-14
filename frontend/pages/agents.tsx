import React from 'react'
import { Card } from '@/components/ui'

export default function AgentControlCenter() {
  return (
    <div className='space-y-6'>
      <Card title='Agent Control Center'>
        <p className='text-muted-foreground'>
          Agent APIs are not implemented by the backend yet.
        </p>

        <p className="text-muted-foreground">No agent records are available.</p>

        <div className='mt-6'>
          <h3 className='text-sm font-medium text-muted-foreground mb-3'>Agent Statistics</h3>
          <div className='grid grid-cols-3 gap-4'>
            <div className='bg-card border border-border rounded-lg p-4'>
              <p className='text-muted-foreground text-sm'>Active Agents</p>
              <p className='text-2xl font-bold text-gray-900'>Unavailable</p>
            </div>
            <div className='bg-card border border-border rounded-lg p-4'>
              <p className='text-muted-foreground text-sm'>Total Executions</p>
              <p className='text-2xl font-bold text-gray-900'>Unavailable</p>
            </div>
            <div className='bg-card border border-border rounded-lg p-4'>
              <p className='text-muted-foreground text-sm'>Avg. Latency</p>
              <p className='text-2xl font-bold text-gray-900'>Unavailable</p>
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}