import { useState, useEffect } from 'react'
import Sidebar from './Sidebar'
import ChatWindow from './ChatWindow'
import HealthBadge from './HealthBadge'
import { getAllChannels } from '../api'

const s = {
  root: { display: 'flex', height: '100vh', overflow: 'hidden' },
  header: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '0 16px', height: 52, background: 'var(--bg-sidebar)',
    borderBottom: '1px solid rgba(0,0,0,0.07)', flexShrink: 0,
  },
  title: { fontWeight: 800, fontSize: 15, color: 'var(--text-heading)', letterSpacing: -0.3 },
  spacer: { flex: 1 },
  username: { fontSize: 13, color: 'var(--text-muted)', fontWeight: 600 },
  logoutBtn: {
    padding: '5px 12px', background: 'rgba(0,0,0,0.06)', color: 'var(--text-muted)',
    fontSize: 13, borderRadius: 6,
  },
  sidebarWrapper: {
    display: 'flex', flexDirection: 'column', width: 240,
    background: 'var(--bg-sidebar)', flexShrink: 0,
  },
  sidebarHeader: {
    height: 52, display: 'flex', alignItems: 'center', padding: '0 14px',
    borderBottom: '1px solid rgba(0,0,0,0.07)', flexShrink: 0,
  },
  body: { display: 'flex', flex: 1, overflow: 'hidden' },
  mainHeader: {
    height: 52, display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
    padding: '0 20px', borderBottom: '1px solid rgba(0,0,0,0.07)',
    background: 'var(--bg-main)', gap: 12, flexShrink: 0,
  },
  mainWrapper: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' },
}

export default function MainLayout({ auth, onLogout }) {
  const [activeChannelId, setActiveChannelId] = useState(null)
  const [channelMap, setChannelMap] = useState({})

  useEffect(() => {
    getAllChannels(auth.token).then((list) => {
      const map = {}
      list.forEach((c) => { map[c.id] = c.name })
      setChannelMap(map)
    }).catch(() => {})
  }, [auth.token])

  function handleSelectChannel(id) {
    setActiveChannelId(id)
    // ensure map has this channel
    getAllChannels(auth.token).then((list) => {
      const map = {}
      list.forEach((c) => { map[c.id] = c.name })
      setChannelMap(map)
    }).catch(() => {})
  }

  return (
    <div style={s.root}>
      <div style={s.sidebarWrapper}>
        <div style={s.sidebarHeader}>
          <span style={s.title}>realtime-hub</span>
        </div>
        <Sidebar
          auth={auth}
          activeChannelId={activeChannelId}
          onSelectChannel={handleSelectChannel}
        />
      </div>

      <div style={s.mainWrapper}>
        <div style={s.mainHeader}>
          <HealthBadge />
          <span style={s.username}>{auth.username}</span>
          <button style={s.logoutBtn} onClick={onLogout}>Sign out</button>
        </div>
        <ChatWindow
          auth={auth}
          channelId={activeChannelId}
          channelName={channelMap[activeChannelId] || ''}
        />
      </div>
    </div>
  )
}
