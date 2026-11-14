import React from 'react'
import { Outlet } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { NavLink } from '@/components/ui/navlink'
import { useAuth } from '@/src/auth'

export default function MainLayout() {
  const { user, logout } = useAuth()
  return (
    <div className="min-h-screen bg-background p-4 md:p-8">
      <header className="mb-8">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-3xl font-bold tracking-tight text-gray-900">
            NEXUS AI
          </h2>
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">{user?.email}</span>
            <Button variant="outline" size="sm" onClick={logout}>Sign out</Button>
          </div>
        </div>
      </header>
      <nav className="mb-6 flex flex-wrap gap-2">
        <NavLink to="/app">Dashboard</NavLink>
        <NavLink to="/app/document-explorer">Documents</NavLink>
        <NavLink to="/app/knowledge-sources">Sources</NavLink>
        <NavLink to="/app/chat">Chat</NavLink>
        <NavLink to="/profile">Profile</NavLink>
      </nav>

      <main>
        <Outlet />
      </main>
    </div>
  )
}