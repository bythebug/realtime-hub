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
  demoBox: {
    marginTop: 20, padding: '12px 14px', background: 'var(--bg-input)',
    border: '1px solid var(--border)', borderRadius: 'var(--radius)',
    fontSize: 12,
  },
  demoLabel: { color: 'var(--text-muted)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6, display: 'block' },
  demoRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 4 },
  demoKey: { color: 'var(--text-muted)' },
  demoVal: { fontFamily: 'monospace', color: 'var(--text-primary)', userSelect: 'all' },
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
          <div style={{ display: 'flex', justifyContent: 'center', marginBottom: 12 }}>
            <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'var(--accent)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
              </svg>
            </div>
          </div>
          <span style={s.logoTitle}>realtime-hub</span>
          <span style={{ textTransform: 'none', letterSpacing: 0 }}>Production-grade real-time messaging system · Flask, Socket.IO, Redis pub/sub, Celery, PostgreSQL, circuit breakers, Prometheus</span>
        </div>
        <div style={{ textAlign: 'center', marginBottom: 20, marginTop: -16 }}>
          <a
            href="https://github.com/bythebug"
            target="_blank"
            rel="noreferrer"
            style={{ fontSize: 12, color: 'var(--text-muted)', display: 'inline-flex', alignItems: 'center', gap: 5 }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z"/>
            </svg>
            github.com/bythebug
          </a>
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

        {tab === 'login' && (
          <div style={s.demoBox}>
            <span style={s.demoLabel}>Demo account</span>
            <div style={s.demoRow}>
              <span style={s.demoKey}>Email</span>
              <span style={s.demoVal}>demo@realtimehub.app</span>
            </div>
            <div style={s.demoRow}>
              <span style={s.demoKey}>Password</span>
              <span style={s.demoVal}>demo1234</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
