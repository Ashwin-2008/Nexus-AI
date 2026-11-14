import React from 'react'
import { Card } from '@/components/ui'

export default function KnowledgeSources() {
  return (
    <div className='space-y-6'>
      <Card title='Data Sources'>
        <p className='text-muted-foreground'>
          Source management is unavailable because connector APIs have not been implemented by the backend.
        </p>
        <div className='grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 mt-6'>
          <div className='group bg-card border border-border rounded-lg p-6 hover:shadow-sm transition-shadow cursor-pointer'>
            <div className='w-12 h-12 rounded-md bg-border flex items-center justify-center shrink-0'>
              <svg viewBox='0 0 24 24' className='w-6 h-6 text-gray-500 group-hover:text-primary transition-colors'>
                <path d='M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z' />
                <path d='M2 4h5v14L2 20V4zm12-2h-3v5c0 3-2 5-5 5s-5-2-5-5v-5H7l5-5 5 5v-5z' />
              </svg>
            </div>
            <h3 className='mt-3 text-sm font-medium'>PDF & DOCX</h3>
            <p className='mt-1 text-xs text-muted-foreground'>Available through Documents</p>
          </div>
          <div className='group bg-card border border-border rounded-lg p-6 hover:shadow-sm transition-shadow cursor-pointer'>
            <div className='w-12 h-12 rounded-md bg-border flex items-center justify-center shrink-0'>
              <svg viewBox='0 0 24 24' className='w-6 h-6 text-gray-500 group-hover:text-primary transition-colors'>
                <path d='M12 22c1.1 0 2-.9 2-2h-2c0 1.1.89 2 2 2zm4.95-7.94h1.5L18.5 9.38l-1.13-1.12c-.17-.16-.44-.16-.6 0l-1.5 1.51.04.03L15.1 6H5.9l-1.43 1.37c-.16.15-.16.41 0 .56l1.42 1.41.04.03L8.9 15.6l1.56 1.55c.15.15.15.41 0 .56l-1.42 1.41-.04.03L7.5 18.1l-1.13 1.12c-.17.16-.44.16-.6 0l-1.5-1.51-.04-.03l1.43-1.37c-.16-.15-.16-.41 0-.56l1.42-1.41.04-.03L9.9 12.6l-1.56-1.55c-.15-.15-.15-.41 0-.56l1.42-1.41z' />
              </svg>
            </div>
            <h3 className='mt-3 text-sm font-medium'>CSV & Excel</h3>
            <p className='mt-1 text-xs text-muted-foreground'>Planned</p>
          </div>
          <div className='group bg-card border border-border rounded-lg p-6 hover:shadow-sm transition-shadow cursor-pointer'>
            <div className='w-12 h-12 rounded-md bg-border flex items-center justify-center shrink-0'>
              <svg viewBox='0 0 24 24' className='w-6 h-6 text-gray-500 group-hover:text-primary transition-colors'>
                <path d='M14 2H6a2 2 0 0 0-2 2v3h2V4h4v3h2c.55 0 1 .45 1 1v9a1 1 0 0 0 1 1h3v2h-3v3h2c1 0 1-.9 1-1v-2c0-.55-.45-1-1-1h-2v-3h2c1 0 1.05.03 1.5.1l3-3h-5l-3 3zm-4 6c1.1 0 2-.9 2-2h-2c0 1.1.89 2 2 2h2c0-1.1-.89-2-2-2H8c-1.1 0-2 .9-2 2h2z' />
              </svg>
            </div>
            <h3 className='mt-3 text-sm font-medium'>Email & Attachments</h3>
            <p className='mt-1 text-xs text-muted-foreground'>Planned</p>
          </div>
        </div>
      </Card>
    </div>
  )
}