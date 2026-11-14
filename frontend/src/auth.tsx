import React, { createContext, useContext, useEffect, useState } from 'react'
import { getCurrentUser, login as loginRequest, logout as logoutRequest, User } from './api'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
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
    getCurrentUser().then(setUser).catch(() => logoutRequest()).finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string) {
    setUser(await loginRequest(email, password))
  }

  function logout() {
    logoutRequest()
    setUser(null)
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth must be used within AuthProvider')
  return context
}
