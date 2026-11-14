import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
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
import DocumentExplorer from '../pages/documents'
import AgentControlCenter from '../pages/agents'
import Analytics from '../pages/analytics'
import SystemMonitoring from '../pages/monitoring'
import Administration from '../pages/admin'

function App() {
  const { user, loading } = useAuth()
  if (loading) return <div className="p-8">Restoring session...</div>
  return (
    <Routes>
      <Route path="/" element={<AuthLayout />}>
        <Route index element={user ? <Navigate to="/app" replace /> : <Login />} />
        <Route path="register" element={<Register />} />
        <Route path="forgot-password" element={<ForgotPassword />} />
        <Route path="profile" element={user ? <UserProfile /> : <Navigate to="/" replace />} />
      </Route>
      <Route path="/app" element={user ? <MainLayout /> : <Navigate to="/" replace />}>
        <Route index element={<Dashboard />} />
        <Route path="chat" element={<ChatWorkspace />} />
        <Route path="knowledge-sources" element={<KnowledgeSources />} />
        <Route path="document-explorer" element={<DocumentExplorer />} />
        <Route path="agent-control-center" element={<AgentControlCenter />} />
        <Route path="analytics" element={<Analytics />} />
        <Route path="system-monitoring" element={<SystemMonitoring />} />
        <Route path="administration" element={<Administration />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App