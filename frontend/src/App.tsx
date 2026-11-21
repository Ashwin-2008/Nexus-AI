import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { Sparkles } from 'lucide-react'
import { useAuth } from './auth'

import AuthLayout from '../layouts/AuthLayout'
import MainLayout from '../layouts/MainLayout'
import Login from '../pages/auth/Login'
import Register from '../pages/auth/Register'
import ForgotPassword from '../pages/auth/ForgotPassword'
import UserProfile from '../pages/auth/UserProfile'

import Dashboard from '../pages/dashboard'
import ChatWorkspace from '../pages/chat'
import KnowledgeSources from '../pages/sources'
import KnowledgeSearch from '../pages/search'
import RagConsole from '../pages/rag'
import DocumentExplorer from '../pages/documents'
import EmailIntelligence from '../pages/email'
import DatabaseIntelligence from '../pages/database'
import Reports from '../pages/reports'
import AgentControlCenter from '../pages/agents'
import Analytics from '../pages/analytics'
import SystemMonitoring from '../pages/monitoring'
import Administration from '../pages/admin'

function App() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <>
        <div className="nx-app-bg">
          <div className="nx-grid-bg" />
          <div className="nx-aurora nx-aurora--one" />
          <div className="nx-aurora nx-aurora--two" />
        </div>
        <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', position: 'relative', zIndex: 1 }}>
          <div className="nx-stack" style={{ alignItems: 'center', gap: 16 }}>
            <span className="nx-logo-mark" style={{ width: 56, height: 56 }}>
              <Sparkles size={24} />
            </span>
            <div style={{ textAlign: 'center' }}>
              <p className="nx-brand__name" style={{ fontSize: 18 }}>NEXUS AI</p>
              <p className="nx-xs nx-muted" style={{ marginTop: 6 }}>Restoring your secure session…</p>
            </div>
            <span className="nx-spinner" style={{ color: 'var(--nx-accent)' }} />
          </div>
        </div>
      </>
    )
  }

  return (
    <Routes>
      <Route path="/" element={<AuthLayout />}>
        <Route index element={user ? <Navigate to="/app" replace /> : <Login />} />
        <Route path="register" element={user ? <Navigate to="/app" replace /> : <Register />} />
        <Route path="forgot-password" element={user ? <Navigate to="/app" replace /> : <ForgotPassword />} />
        <Route path="profile" element={<Navigate to={user ? '/app/profile' : '/'} replace />} />
      </Route>

      <Route path="/app" element={user ? <MainLayout /> : <Navigate to="/" replace />}>
        <Route index element={<Dashboard />} />
        <Route path="chat" element={<ChatWorkspace />} />
        <Route path="search" element={<KnowledgeSearch />} />
        <Route path="rag" element={<RagConsole />} />
        <Route path="knowledge-sources" element={<KnowledgeSources />} />
        <Route path="document-explorer" element={<DocumentExplorer />} />
        <Route path="email" element={<EmailIntelligence />} />
        <Route path="database" element={<DatabaseIntelligence />} />
        <Route path="reports" element={<Reports />} />
        <Route path="agent-control-center" element={<AgentControlCenter />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="system-monitoring" element={<SystemMonitoring />} />
        <Route path="administration" element={<Administration />} />
        <Route path="profile" element={<UserProfile />} />
      </Route>

      <Route path="*" element={<Navigate to={user ? '/app' : '/'} replace />} />
    </Routes>
  )
}

export default App
