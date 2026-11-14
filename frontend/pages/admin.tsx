import React from 'react'
import { Card, Table, TableBody, TableHeader, TableRow, TableCell, TableHead } from '@/components/ui'

export default function Administration() {
  return (
    <div className='space-y-6'>
      <Card title='User Management'>
        <p className='text-muted-foreground'>
          User management and audit APIs are not implemented by the backend yet.
        </p>

        <Table className='w-full rounded-lg border border-border'>
          <TableHeader>
            <TableRow>
              <TableHead>User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            <TableRow><TableCell className="p-3">Unavailable</TableCell><TableCell className="p-3">Unavailable</TableCell><TableCell className="p-3">Unavailable</TableCell><TableCell className="p-3">Unavailable</TableCell><TableCell className="p-3">Unavailable</TableCell></TableRow>
          </TableBody>
        </Table>

        <div className='mt-6'>
          <h3 className='text-sm font-medium text-muted-foreground mb-3'>Organization Roles</h3>
          <div className='grid grid-cols-3 gap-3'>
            <div className='bg-card border border-border rounded-lg p-3'>
              <p className='text-caption text-muted-foreground'>Admin</p>
              <p className='text-lg font-bold text-gray-900'>Full access</p>
            </div>
            <div className='bg-card border border-border rounded-lg p-3'>
              <p className='text-caption text-muted-foreground'>User</p>
              <p className='text-lg font-bold text-gray-900'>Standard access</p>
            </div>
            <div className='bg-card border border-border rounded-lg p-3'>
              <p className='text-caption text-muted-foreground'>Viewer</p>
              <p className='text-lg font-bold text-gray-900'>Read-only access</p>
            </div>
          </div>
        </div>
      </Card>

      <Card title='Audit Logs'>
        <p className='text-muted-foreground text-sm'>
          Recent activity and system changes.
        </p>
        <div className='overflow-x-auto'>
          <table className='w-full rounded-lg border border-border'>
            <thead>
              <tr className='text-left text-sm text-muted-foreground border-b'>
                <th className='p-3'>Timestamp</th>
                <th className='p-3'>User</th>
                <th className='p-3'>Action</th>
                <th className='p-3'>Details</th>
              </tr>
            </thead>
            <tbody><tr><td className="p-3" colSpan={4}>Audit history unavailable.</td></tr></tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}