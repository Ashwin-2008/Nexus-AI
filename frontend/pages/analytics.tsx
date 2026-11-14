import React from 'react'
import { Card } from '@/components/ui'
import { AlertCircle, CheckCircle, Clock, TrendingUp, MapPin, LogOut } from 'lucide-react'

export default function Analytics() {
  return (
    <div className='space-y-6'>
      <Card title='Retrieval Metrics'>
        <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4'>
          <div className='bg-card border border-border rounded-lg p-6'>
            <div className='w-6 h-6 mx-auto mb-4' />
            <p className='text-muted-foreground text-sm'>Total Queries</p>
            <p className='text-3xl font-bold text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-6'>
            <AlertCircle className='w-6 h-6 mx-auto mb-4 text-error' />
            <p className='text-muted-foreground text-sm'>Failed Retrievals</p>
            <p className='text-3xl font-bold text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-6'>
            <Clock className='w-6 h-6 mx-auto mb-4' />
            <p className='text-muted-foreground text-sm'>Avg. Latency</p>
            <p className='text-3xl font-bold text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-6'>
            <TrendingUp className='w-6 h-6 mx-auto mb-4 text-success' />
            <p className='text-muted-foreground text-sm'>Success Rate</p>
            <p className='text-3xl font-bold text-gray-900'>Unavailable</p>
          </div>
        </div>
      </Card>

      <Card title='Answer Quality'>
        <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4'>
          <div className='bg-card border border-border rounded-lg p-6'>
            <CheckCircle className='w-6 h-6 mx-auto mb-4 text-success' />
            <p className='text-muted-foreground text-sm'>Citation Accuracy</p>
            <p className='text-3xl font-bold text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-6'>
            <p className='w-6 h-6 mx-auto mb-4' />
            <p className='text-muted-foreground text-sm'>Relevant Results</p>
            <p className='text-3xl font-bold text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-6'>
            <LogOut className='w-6 h-6 mx-auto mb-4' />
            <p className='text-muted-foreground text-sm'>Model Costs</p>
            <p className='text-3xl font-bold text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-6'>
            <MapPin className='w-6 h-6 mx-auto mb-4' />
            <p className='text-muted-foreground text-sm'>Tokens Processed</p>
            <p className='text-3xl font-bold text-gray-900'>Unavailable</p>
          </div>
        </div>
      </Card>

      <Card title='System Performance'>
        <div className='grid grid-cols-2 gap-4'>
          <div className='bg-card border border-border rounded-lg h-full p-6 flex flex-col justify-end'>
            <div className='w-24 h-12 mx-auto mb-4' />
            <p className='text-xs text-muted-foreground mb-2'>Last 24h</p>
            <p className='text-lg font-medium text-gray-900'>Unavailable</p>
            <p className='text-xs text-muted-foreground'>Uptime</p>
          </div>
          <div className='bg-card border border-border rounded-lg h-full p-6 flex flex-col justify-end'>
            <div className='w-24 h-12 mx-auto mb-4' />
            <p className='text-xs text-muted-foreground mb-2'>Queue Depth</p>
            <p className='text-lg font-medium text-gray-900'>Unavailable</p>
            <p className='text-xs text-muted-foreground'>Pending jobs</p>
          </div>
        </div>
      </Card>
    </div>
  )
}