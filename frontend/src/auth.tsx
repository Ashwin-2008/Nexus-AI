import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { getCurrentUser, login as loginRequest, logout as logoutRequest, User } from './api'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!sessionStorage.getItem('nexus_access_token')) {
      setLoading(false)
      return
    }
    getCurrentUser()
      .then(setUser)
      .catch(() => {
        logoutRequest()
        setUser(null)
      })
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    const onUnauthorized = () => {
      logoutRequest()
      setUser(null)
    }
    window.addEventListener('nexus:unauthorized', onUnauthorized)
    return () => window.removeEventListener('nexus:unauthorized', onUnauthorized)
  }, [])

  async function login(email: string, password: string) {
    const nextUser = await loginRequest(email, password)
    setUser(nextUser)
  }

  function logout() {
    logoutRequest()
    setUser(null)
  }

  const refreshUser = useCallback(async () => {
    setUser(await getCurrentUser())
  }, [])

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
