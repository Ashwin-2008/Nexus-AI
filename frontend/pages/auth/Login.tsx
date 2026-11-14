import React, { useState } from 'react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/src/auth'
import { useNavigate } from 'react-router-dom'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const { login } = useAuth()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try { await login(email, password); navigate('/app') }
    catch (err) { setError(err instanceof Error ? err.message : 'Unable to sign in') }
    finally { setLoading(false) }
  }

  return (
    <div className="max-w-md w-full space-y-6">
      <h2 className="text-2xl font-bold tracking-tight text-gray-900">Sign in</h2>

      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <Input
          type="email"
          placeholder="Enter your email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Input
          type="password"
          placeholder="Enter your password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error && (
          <div className="text-sm text-red-600">{error}</div>
        )}
        <Button type="submit" disabled={loading}>{loading ? 'Signing in...' : 'Sign in'}</Button>
      </form>

      <p className="text-sm text-muted-foreground">
        Don't have an account? <a href="/register" className="underline font-medium">Register</a>
      </p>
    </div>
  )
}