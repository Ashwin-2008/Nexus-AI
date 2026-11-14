import React, { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { register } from '@/src/api'
import { useNavigate } from 'react-router-dom'

export default function Register() {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [organizationName, setOrganizationName] = useState('')
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null); setLoading(true)
    try { await register(email, password, name, organizationName); navigate('/') }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to register') }
    finally { setLoading(false) }
  }

  return (
    <div className="max-w-md w-full space-y-6">
      <h2 className="text-2xl font-bold tracking-tight text-gray-900">Create account</h2>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <Input
          placeholder="Organization name"
          value={organizationName}
          onChange={(e) => setOrganizationName(e.target.value)}
          required
        />
        <Input
          placeholder="Full name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
        <Input
          type="email"
          placeholder="Enter your email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          type="password"
          placeholder="Create a password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && (
          <div className="text-sm text-red-600">{error}</div>
        )}
        <Button type="submit" disabled={loading}>{loading ? 'Creating account...' : 'Create account'}</Button>
      </form>

      <p className="text-sm text-muted-foreground">
        Already have an account? <a href="/" className="underline font-medium">Sign in</a>
      </p>
    </div>
  )
}