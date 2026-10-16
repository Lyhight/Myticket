import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { api } from '../api/client'
import type { User } from '../types'

type AuthValue = { user: User | null; loading: boolean; login: (email: string, password: string) => Promise<void>; register: (email: string, password: string) => Promise<void>; logout: () => Promise<void> }
const AuthContext = createContext<AuthValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  async function loadUser() {
    try { setUser(await api<User>('/users/me')) } catch { setUser(null) }
    finally { setLoading(false) }
  }
  useEffect(() => {
    localStorage.removeItem('myticket_token')
    void loadUser()
  }, [])

  async function login(email: string, password: string) {
    await api('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
    await loadUser()
  }
  async function register(email: string, password: string) {
    await api('/users', { method: 'POST', body: JSON.stringify({ email, password }) })
    await login(email, password)
  }
  async function logout() {
    try { await api('/auth/logout', { method: 'POST' }) }
    finally { setUser(null) }
  }
  return <AuthContext.Provider value={{ user, loading, login, register, logout }}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const value = useContext(AuthContext)
  if (!value) throw new Error('AuthContext missing')
  return value
}
