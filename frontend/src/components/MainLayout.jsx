import { useState, useEffect, useRef } from 'react'
import Sidebar from './Sidebar'
import ChatWindow from './ChatWindow'
import HealthBadge from './HealthBadge'
import { getAllChannels, getNotifications, markAllNotificationsRead } from '../api'
import { getSocket } from '../socket'

const s = {
  root: { display: 'flex', height: '100vh', overflow: 'hidden' },
  title: { fontWeight: 800, fontSize: 15, color: 'var(--text-heading)', letterSpacing: -0.3 },
  username: { fontSize: 13, color: 'var(--text-muted)', fontWeight: 600 },
  logoutBtn: {
    padding: '5px 12px', background: 'rgba(0,0,0,0.06)', color: 'var(--text-muted)',
    fontSize: 13, borderRadius: 6,
  },
  bellWrap: { position: 'relative' },
  bellBtn: {
    position: 'relative', padding: '5px 10px', background: 'rgba(0,0,0,0.06)',
    color: 'var(--text-muted)', fontSize: 16, borderRadius: 6,
  },
  badge: {
    position: 'absolute', top: -4, right: -4,
    background: 'var(--accent)', color: '#fff',
    fontSize: 10, fontWeight: 700, borderRadius: 10,
    padding: '1px 5px', lineHeight: 1.4,
  },
  dropdown: {
    position: 'absolute', top: 36, right: 0, width: 300, zIndex: 100,
    background: 'var(--bg-main)', border: '1px solid var(--border)',
    borderRadius: 8, boxShadow: '0 4px 16px rgba(0,0,0,0.10)', overflow: 'hidden',
  },
  dropdownHeader: {
    padding: '10px 14px', borderBottom: '1px solid var(--border)',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  },
  dropdownTitle: { fontSize: 13, fontWeight: 700, color: 'var(--text-heading)' },
  markAllBtn: { fontSize: 11, color: 'var(--accent)', background: 'none', borderRadius: 4, padding: '2px 6px' },
  dropdownList: { maxHeight: 320, overflowY: 'auto' },
  notifItem: (hovered) => ({
    padding: '10px 14px', cursor: 'pointer',
    background: hovered ? 'var(--bg-input)' : 'transparent',
    borderBottom: '1px solid var(--border)',
    display: 'flex', flexDirection: 'column', gap: 2,
  }),
  notifChannel: { fontSize: 13, fontWeight: 600, color: 'var(--accent)' },
  notifSub: { fontSize: 12, color: 'var(--text-muted)' },
  empty: { padding: '20px 14px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 13 },
  sidebarWrapper: {
    display: 'flex', flexDirection: 'column', width: 240,
    background: 'var(--bg-sidebar)', flexShrink: 0,
  },
  sidebarHeader: {
    height: 52, display: 'flex', alignItems: 'center', padding: '0 14px',
    borderBottom: '1px solid rgba(0,0,0,0.07)', flexShrink: 0,
  },
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
  const [notifications, setNotifications] = useState([])
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [hoveredId, setHoveredId] = useState(null)
  const dropdownRef = useRef(null)

  useEffect(() => {
    getNotifications(auth.token).then(setNotifications).catch(() => {})
  }, [auth.token])

  useEffect(() => {
    const socket = getSocket()
    if (!socket) return
    function onNotification(data) {
      setNotifications((prev) => [data, ...prev])
    }
    socket.on('notification', onNotification)
    return () => socket.off('notification', onNotification)
  }, [])

  useEffect(() => {
    function handleClickOutside(e) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setDropdownOpen(false)
      }
    }
    if (dropdownOpen) document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [dropdownOpen])

  useEffect(() => {
    getAllChannels(auth.token).then((list) => {
      const map = {}
      list.forEach((c) => { map[c.id] = c.name })
      setChannelMap(map)
    }).catch(() => {})
  }, [auth.token])

  function handleSelectChannel(id) {
    setActiveChannelId(id)
    getAllChannels(auth.token).then((list) => {
      const map = {}
      list.forEach((c) => { map[c.id] = c.name })
      setChannelMap(map)
    }).catch(() => {})
  }

  async function handleMarkAllRead() {
    try {
      await markAllNotificationsRead(auth.token)
      setNotifications([])
      setDropdownOpen(false)
    } catch {}
  }

  async function handleNotificationClick(notif) {
    if (notif.channel_id) handleSelectChannel(notif.channel_id)
    setDropdownOpen(false)
    try {
      await markAllNotificationsRead(auth.token)
      setNotifications([])
    } catch {}
  }

  const unreadCount = notifications.length

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

          <div style={s.bellWrap} ref={dropdownRef}>
            <button style={s.bellBtn} onClick={() => setDropdownOpen((o) => !o)} title="Notifications">
              🔔
              {unreadCount > 0 && (
                <span style={s.badge}>{unreadCount > 99 ? '99+' : unreadCount}</span>
              )}
            </button>

            {dropdownOpen && (
              <div style={s.dropdown}>
                <div style={s.dropdownHeader}>
                  <span style={s.dropdownTitle}>Notifications</span>
                  {unreadCount > 0 && (
                    <button style={s.markAllBtn} onClick={handleMarkAllRead}>Mark all read</button>
                  )}
                </div>
                <div style={s.dropdownList}>
                  {notifications.length === 0 ? (
                    <div style={s.empty}>You're all caught up</div>
                  ) : (
                    notifications.map((n) => (
                      <div
                        key={n.id ?? n.notification_id ?? Math.random()}
                        style={s.notifItem(hoveredId === (n.id ?? n.notification_id))}
                        onMouseEnter={() => setHoveredId(n.id ?? n.notification_id)}
                        onMouseLeave={() => setHoveredId(null)}
                        onClick={() => handleNotificationClick(n)}
                      >
                        <span style={s.notifChannel}>
                          #{channelMap[n.channel_id] || `channel ${n.channel_id}`}
                        </span>
                        <span style={s.notifSub}>New message</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

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
