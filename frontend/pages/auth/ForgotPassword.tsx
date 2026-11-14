import React, { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'

export default function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    // TODO: Implement forgot password
    setError('Password recovery temporarily unavailable')
  }

  return (
    <div className="max-w-md w-full space-y-6">
      <h2 className="text-2xl font-bold tracking-tight text-gray-900">Forgot password</h2>

      <p className="text-muted-foreground">
        Enter your email address below and we'll send you a link to reset your password.
      </p>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <Input
          type="email"
          placeholder="Enter your email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        {error && (
          <div className="text-sm text-red-600">{error}</div>
        )}
        <Button type="submit">Send reset link</Button>
      </form>

      <p className="text-sm text-muted-foreground">
        <a href="/" className="underline font-medium">Remember your password?</a>
      </p>
    </div>
  )
}