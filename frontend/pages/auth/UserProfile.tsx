import React from 'react'
import { useAuth } from '@/src/auth'

export default function UserProfile() {
  const { user } = useAuth()

  return (
    <div className="max-w-md w-full space-y-6">
      <h2 className="text-2xl font-bold tracking-tight text-gray-900">Profile</h2>

      <p className="text-sm">Name: {user?.full_name || 'Not provided'}</p>
      <p className="text-sm">Email: {user?.email}</p>
      <p className="text-sm">Role: {user?.role}</p>
      <p className="text-sm text-muted-foreground">Profile editing is unavailable because no backend update endpoint exists.</p>
    </div>
  )
}