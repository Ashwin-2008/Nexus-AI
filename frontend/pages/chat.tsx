import React from 'react'
import { Button, Card, Input } from '@/components/ui'

export default function ChatWorkspace() {
  const [input, setInput] = React.useState('')
  return (
    <Card title="Chat workspace">
      <p className="mb-6 text-muted-foreground">
        Chat is unavailable because the backend RAG and streaming endpoint has not been implemented.
      </p>
      <form className="flex gap-2" onSubmit={(event) => { event.preventDefault(); setInput('') }}>
        <Input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask a question when chat is available" disabled />
        <Button type="submit" disabled>Send</Button>
      </form>
    </Card>
  )
}
