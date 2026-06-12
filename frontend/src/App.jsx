import { useState, useEffect, useCallback } from 'react'
import AuthPage from './components/AuthPage'
import MainLayout from './components/MainLayout'
import { connect, disconnect } from './socket'

function loadAuth() {
  try {
    const token = localStorage.getItem('rh_token')
    const user_id = localStorage.getItem('rh_user_id')
    const username = localStorage.getItem('rh_username')
    if (token && user_id) return { token, user_id: Number(user_id), username }
  } catch {}
  return null
}

export default function App() {
  const [auth, setAuth] = useState(loadAuth)

  useEffect(() => {
    if (auth?.token) {
      connect(auth.token)
    }
    return () => disconnect()
  }, [auth?.token])

  const handleLogin = useCallback((data) => {
    localStorage.setItem('rh_token', data.token)
    localStorage.setItem('rh_user_id', data.user_id)
    localStorage.setItem('rh_username', data.username)
    setAuth({ token: data.token, user_id: data.user_id, username: data.username })
  }, [])

  const handleLogout = useCallback(() => {
    localStorage.removeItem('rh_token')
    localStorage.removeItem('rh_user_id')
    localStorage.removeItem('rh_username')
    disconnect()
    setAuth(null)
  }, [])

  if (!auth) return <AuthPage onLogin={handleLogin} />
  return <MainLayout auth={auth} onLogout={handleLogout} />
}
