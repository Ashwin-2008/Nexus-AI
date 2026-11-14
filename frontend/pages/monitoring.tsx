import React from 'react'
import { Card, Table, TableBody, TableHeader, TableRow, TableCell, TableHead } from '@/components/ui'

export default function SystemMonitoring() {
  return (
    <div className='space-y-6'>
      <Card title='Backend Health'>
        <Table className='w-full rounded-lg border border-border'>
          <TableHeader>
            <TableRow>
              <TableHead>Component</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Latency</TableHead>
              <TableHead>Last Check</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow><TableCell className='p-3'>Health service</TableCell><TableCell className='p-3'>Unavailable</TableCell><TableCell className='p-3'>Unavailable</TableCell><TableCell className='p-3'>Unavailable</TableCell></TableRow>
          </TableBody>
        </Table>
      </Card>

      <Card title='Worker Status'>
        <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-4'>
          <div className='bg-card border border-border rounded-lg p-4'>
            <p className='text-muted-foreground text-sm'>Workers Active</p>
            <p className='text-2xl font-bold text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-4'>
            <p className='text-muted-foreground text-sm'>Jobs Processed</p>
            <p className='text-2xl font-bold text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-4'>
            <p className='text-muted-foreground text-sm'>Queue Length</p>
            <p className='text-2xl font-bold text-gray-900'>Unavailable</p>
          </div>
        </div>
      </Card>

      <Card title='Connector Health'>
        <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4'>
          <div className='bg-card border border-border rounded-lg p-3'>
            <p className='text-caption text-muted-foreground'>SQL Databases</p>
            <p className='text-lg font-medium text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-3'>
            <p className='text-caption text-muted-foreground'>REST APIs</p>
            <p className='text-lg font-medium text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-3'>
            <p className='text-caption text-muted-foreground'>Google Drive</p>
            <p className='text-lg font-medium text-gray-900'>Unavailable</p>
          </div>
          <div className='bg-card border border-border rounded-lg p-3'>
            <p className='text-caption text-muted-foreground'>GitHub</p>
            <p className='text-lg font-medium text-gray-900'>Unavailable</p>
          </div>
        </div>
      </Card>
    </div>
  )
}