import React from 'react'
import { Card, Input, Button } from '@/components/ui'
import { Document, listDocuments, retryDocument, uploadDocument } from '@/src/api'

export default function DocumentExplorer() {
  const [search, setSearch] = React.useState('')
  const [files, setFiles] = React.useState<Document[]>([])
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(true)
  const fileInput = React.useRef<HTMLInputElement>(null)
  const originalFiles = React.useMemo(() => files, [files])

  React.useEffect(() => { listDocuments().then(setFiles).catch((e) => setError(e.message)).finally(() => setLoading(false)) }, [])

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value)
  }

  // Reset files when search is cleared
  const visibleFiles = originalFiles.filter((file) => file.filename.toLowerCase().includes(search.toLowerCase()))
  async function handleUpload(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    try { const uploaded = await uploadDocument(file); setFiles((current) => [uploaded, ...current]); setError(null) }
    catch (e) { setError(e instanceof Error ? e.message : 'Upload failed') }
  }

  return (
    <div className='space-y-6'>
      <Card title='Document Explorer'>
        <div className='flex items-center gap-3 mb-4'>
          <Input
            placeholder='Search documents...'
            value={search}
            onChange={handleSearch}
            className='flex-1'
          />
          <input ref={fileInput} type="file" className="hidden" accept=".pdf,.docx,.txt,.csv,.xlsx" onChange={handleUpload} />
          <Button variant='outline' size='sm' onClick={() => fileInput.current?.click()}>
            Upload
          </Button>
        </div>

        <div className='overflow-x-auto'>
          <table className='w-full rounded-lg border border-border'>
            <thead>
              <tr className='text-left text-sm text-muted-foreground border-b'>
                <th className='p-3'>Name</th>
                <th className='p-3'>Type</th>
                <th className='p-3'>Size</th>
                <th className='p-3'>Status</th>
                <th className='p-3'>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleFiles.map((file) => (
                <tr key={file.id} className='align-middle border-b'>
                  <td className='p-3 font-medium'>
                    {file.filename}
                  </td>
                  <td className='p-3 text-sm'>
                    {file.content_type}
                  </td>
                  <td className='p-3 text-sm'>
                    {(file.file_size / 1024).toFixed(1)} KB
                  </td>
                  <td className='p-3'>
                    <span
                      className={`inline-flex items-center rounded-md px-2 py-1 text-xs font-medium ${
                        file.status === 'completed'
                          ? 'bg-green-100 text-green-800'
                          : file.status === 'processing' || file.status === 'pending'
                          ? 'bg-yellow-100 text-yellow-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {file.status}
                    </span>
                  </td>
                  <td className='p-3'>
                    {file.status === 'failed' && <Button variant='ghost' size='sm' className='text-xs' onClick={async () => {
                      try {
                        const updated = await retryDocument(file.id)
                        setFiles((current) => current.map((item) => item.id === file.id ? updated : item))
                      } catch (e) {
                        setError(e instanceof Error ? e.message : 'Retry failed')
                      }
                    }}>Retry</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {error && <p className="text-red-600">{error}</p>}
        {loading && <p className="text-muted-foreground">Loading documents...</p>}
        {!loading && visibleFiles.length === 0 && (
          <p className='text-muted-foreground text-center py-8'>
            No documents found. Upload your first document.
          </p>
        )}
      </Card>
    </div>
  )
}