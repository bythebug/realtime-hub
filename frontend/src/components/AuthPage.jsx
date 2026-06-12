import { useState } from 'react'
import { login, register } from '../api'

const s = {
  page: {
    minHeight: '100vh', display: 'flex', alignItems: 'center',
    justifyContent: 'center', background: 'var(--bg-main)',
  },
  card: {
    background: 'var(--bg-auth)', borderRadius: 12, padding: '40px 36px',
    width: 420, boxShadow: '0 4px 24px rgba(0,0,0,0.10)', border: '1px solid var(--border)',
  },
  logo: {
    textAlign: 'center', marginBottom: 28,
    fontSize: 13, color: 'var(--text-muted)', letterSpacing: 1, textTransform: 'uppercase',
  },
  logoTitle: { fontSize: 24, fontWeight: 700, color: 'var(--text-heading)', display: 'block', marginBottom: 4 },
  tabs: { display: 'flex', gap: 0, marginBottom: 28, borderBottom: '2px solid var(--border)' },
  tab: (active) => ({
    flex: 1, padding: '10px 0', background: 'transparent', borderRadius: 0,
    color: active ? 'var(--text-heading)' : 'var(--text-muted)',
    borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
    marginBottom: -2, fontSize: 15, fontWeight: active ? 600 : 400,
  }),
  field: { marginBottom: 16 },
  label: { display: 'block', fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase', letterSpacing: 0.5 },
  input: { width: '100%' },
  btn: {
    width: '100%', padding: '12px', marginTop: 8,
    background: 'var(--accent)', color: '#fff', fontSize: 15, fontWeight: 600, borderRadius: 'var(--radius)',
  },
  error: {
    marginTop: 12, padding: '10px 14px', background: 'rgba(237,66,69,0.15)',
    border: '1px solid rgba(237,66,69,0.4)', borderRadius: 'var(--radius)',
    color: '#ed4245', fontSize: 13,
  },
}

export default function AuthPage({ onLogin }) {
  const [tab, setTab] = useState('login')
  const [form, setForm] = useState({ username: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }))

  async function submit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = tab === 'login'
        ? await login(form.email, form.password)
        : await register(form.username, form.email, form.password)
      onLogin(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s.page}>
      <div style={s.card}>
        <div style={s.logo}>
          <span style={s.logoTitle}>realtime-hub</span>
          Real-time messaging
        </div>

        <div style={s.tabs}>
          <button style={s.tab(tab === 'login')} onClick={() => setTab('login')}>Sign In</button>
          <button style={s.tab(tab === 'register')} onClick={() => setTab('register')}>Create Account</button>
        </div>

        <form onSubmit={submit}>
          {tab === 'register' && (
            <div style={s.field}>
              <label style={s.label}>Username</label>
              <input style={s.input} value={form.username} onChange={set('username')} placeholder="cooluser" autoFocus />
            </div>
          )}
          <div style={s.field}>
            <label style={s.label}>Email</label>
            <input style={s.input} type="email" value={form.email} onChange={set('email')} placeholder="you@example.com" autoFocus={tab === 'login'} />
          </div>
          <div style={s.field}>
            <label style={s.label}>Password</label>
            <input style={s.input} type="password" value={form.password} onChange={set('password')} placeholder="••••••••" />
          </div>
          {error && <div style={s.error}>{error}</div>}
          <button type="submit" style={s.btn} disabled={loading}>
            {loading ? 'Please wait…' : tab === 'login' ? 'Sign In' : 'Create Account'}
          </button>
        </form>
      </div>
    </div>
  )
}
