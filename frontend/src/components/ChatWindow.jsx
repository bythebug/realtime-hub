import { useState, useEffect, useRef, useCallback } from 'react'
import { getMessages, getUser, deleteMessage as apiDeleteMessage } from '../api'
import { getSocket } from '../socket'

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const COLORS = ['#5865f2', '#c0392b', '#2d8a4e', '#d07e00', '#0099e5', '#8e44ad']
function userColor(userId) { return COLORS[userId % COLORS.length] }
function initials(name) { return name ? name.slice(0, 2).toUpperCase() : '??' }

const PAGE = 50

const s = {
  root: { flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-main)' },
  header: {
    padding: '0 20px', height: 52, display: 'flex', alignItems: 'center', gap: 10,
    borderBottom: '1px solid rgba(0,0,0,0.07)', flexShrink: 0,
  },
  headerHash: { color: 'var(--text-muted)', fontSize: 20, fontWeight: 300 },
  headerName: { fontWeight: 700, color: 'var(--text-heading)', fontSize: 16 },
  messages: { flex: 1, overflowY: 'auto', padding: '12px 20px 0' },
  loadMoreRow: { textAlign: 'center', padding: '4px 0 16px' },
  loadMoreBtn: {
    padding: '5px 16px', background: 'var(--bg-input)', color: 'var(--text-muted)',
    fontSize: 12, borderRadius: 6, border: '1px solid var(--border)',
  },
  empty: { color: 'var(--text-muted)', fontSize: 14, textAlign: 'center', marginTop: 60 },
  msgRow: (hovered) => ({
    display: 'flex', gap: 14, marginBottom: 16, padding: '4px 8px',
    borderRadius: 6, background: hovered ? 'var(--bg-input)' : 'transparent',
    position: 'relative',
  }),
  avatar: (userId) => ({
    width: 36, height: 36, borderRadius: '50%', flexShrink: 0, marginTop: 2,
    background: userColor(userId), display: 'flex', alignItems: 'center',
    justifyContent: 'center', fontSize: 12, fontWeight: 700, color: '#fff',
  }),
  msgBody: { minWidth: 0, flex: 1 },
  msgMeta: { display: 'flex', gap: 8, alignItems: 'baseline', marginBottom: 2 },
  msgUser: (userId) => ({ fontWeight: 600, fontSize: 14, color: userColor(userId) }),
  msgTime: { fontSize: 11, color: 'var(--text-muted)' },
  msgContent: { fontSize: 15, color: 'var(--text-primary)', wordBreak: 'break-word' },
  deleteBtn: {
    position: 'absolute', right: 8, top: 6,
    padding: '2px 8px', background: 'rgba(214,54,56,0.1)', color: 'var(--danger)',
    fontSize: 11, borderRadius: 4,
  },
  systemMsg: {
    textAlign: 'center', color: 'var(--text-muted)', fontSize: 12,
    padding: '2px 0 12px', fontStyle: 'italic',
  },
  inputArea: { padding: '16px 20px', flexShrink: 0 },
  inputRow: {
    display: 'flex', gap: 10, background: 'var(--bg-input)',
    borderRadius: 'var(--radius)', padding: '4px 4px 4px 14px',
    border: '1px solid rgba(0,0,0,0.07)',
  },
  input: {
    flex: 1, background: 'transparent', border: 'none', padding: '8px 0',
    fontSize: 15, resize: 'none', height: 36, lineHeight: '20px',
    color: 'var(--text-primary)',
  },
  sendBtn: {
    padding: '8px 16px', background: 'var(--accent)', color: '#fff',
    borderRadius: 6, fontSize: 14, fontWeight: 600, alignSelf: 'flex-end',
  },
  placeholder: {
    flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', color: 'var(--text-muted)', gap: 12,
  },
}

export default function ChatWindow({ auth, channelId, channelName }) {
  const [messages, setMessages] = useState([])
  const [events, setEvents] = useState([])
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [offset, setOffset] = useState(0)
  const [hasMore, setHasMore] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [usernames, setUsernames] = useState({})
  const [hoveredMsgId, setHoveredMsgId] = useState(null)
  const bottomRef = useRef(null)
  const scrollRef = useRef(null)

  const addMessage = useCallback((msg) => {
    setMessages((prev) => {
      if (prev.some((m) => m.id === msg.id)) return prev
      return [...prev, msg]
    })
  }, [])

  // fetch usernames for any user_ids not yet resolved
  useEffect(() => {
    const missing = [...new Set(messages.map((m) => m.user_id))]
      .filter((id) => id != null && id !== auth.user_id && !usernames[id])
    if (!missing.length) return
    Promise.all(
      missing.map((id) =>
        getUser(auth.token, id)
          .then((u) => [id, u.username])
          .catch(() => [id, `User ${id}`])
      )
    ).then((pairs) => {
      setUsernames((prev) => ({ ...prev, ...Object.fromEntries(pairs) }))
    })
  }, [messages]) // eslint-disable-line react-hooks/exhaustive-deps

  function getUsername(userId) {
    if (userId === auth.user_id) return auth.username
    return usernames[userId] || `User ${userId}`
  }

  useEffect(() => {
    if (!channelId) return
    setMessages([])
    setEvents([])
    setOffset(0)
    setHasMore(false)

    getMessages(auth.token, channelId, { limit: PAGE, offset: 0 })
      .then((msgs) => {
        setMessages([...msgs].reverse())
        setHasMore(msgs.length === PAGE)
        setOffset(msgs.length)
      })
      .catch(() => {})

    const socket = getSocket()
    if (!socket) return
    socket.emit('join', { channel_id: channelId })

    function onNewMessage(msg) {
      if (msg.channel_id === channelId) addMessage(msg)
    }
    function onUserJoined(data) {
      if (data.channel_id === channelId)
        setEvents((prev) => [...prev, { key: Date.now(), text: `User ${data.user_id} joined` }])
    }
    function onUserLeft(data) {
      if (data.channel_id === channelId)
        setEvents((prev) => [...prev, { key: Date.now(), text: `User ${data.user_id} left` }])
    }

    socket.on('new_message', onNewMessage)
    socket.on('user_joined', onUserJoined)
    socket.on('user_left', onUserLeft)

    return () => {
      socket.emit('leave', { channel_id: channelId })
      socket.off('new_message', onNewMessage)
      socket.off('user_joined', onUserJoined)
      socket.off('user_left', onUserLeft)
    }
  }, [channelId, auth.token, addMessage])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages.length, events.length])

  async function loadEarlier() {
    if (loadingMore) return
    setLoadingMore(true)
    try {
      const older = await getMessages(auth.token, channelId, { limit: PAGE, offset })
      const ordered = [...older].reverse()
      const el = scrollRef.current
      const prevScrollHeight = el?.scrollHeight ?? 0
      setMessages((prev) => [...ordered, ...prev])
      setHasMore(older.length === PAGE)
      setOffset((o) => o + older.length)
      requestAnimationFrame(() => {
        if (el) el.scrollTop = el.scrollHeight - prevScrollHeight
      })
    } catch {}
    setLoadingMore(false)
  }

  async function send(e) {
    e.preventDefault()
    if (!text.trim() || sending) return
    const socket = getSocket()
    if (!socket) return
    setSending(true)
    socket.emit('message', { channel_id: channelId, content: text.trim() })
    setText('')
    setSending(false)
  }

  async function handleDelete(msgId) {
    try {
      await apiDeleteMessage(auth.token, msgId)
      setMessages((prev) => prev.filter((m) => m.id !== msgId))
    } catch {}
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(e) }
  }

  if (!channelId) {
    return (
      <div style={{ ...s.root, ...s.placeholder }}>
        <span style={{ fontSize: 48 }}>💬</span>
        <span style={{ fontSize: 18, fontWeight: 600, color: 'var(--text-heading)' }}>No channel selected</span>
        <span style={{ fontSize: 14 }}>Select a channel from the sidebar or join one to get started.</span>
      </div>
    )
  }

  const allItems = [
    ...messages.map((m) => ({ type: 'msg', data: m, sort: m.created_at })),
    ...events.map((e) => ({ type: 'evt', data: e, sort: String(e.key) })),
  ].sort((a, b) => (a.sort < b.sort ? -1 : 1))

  return (
    <div style={s.root}>
      <div style={s.header}>
        <span style={s.headerHash}>#</span>
        <span style={s.headerName}>{channelName}</span>
      </div>

      <div style={s.messages} ref={scrollRef}>
        {hasMore && (
          <div style={s.loadMoreRow}>
            <button style={s.loadMoreBtn} onClick={loadEarlier} disabled={loadingMore}>
              {loadingMore ? 'Loading…' : 'Load earlier messages'}
            </button>
          </div>
        )}
        {allItems.length === 0 && (
          <div style={s.empty}>No messages yet. Be the first to say something!</div>
        )}
        {allItems.map((item) =>
          item.type === 'evt' ? (
            <div key={item.data.key} style={s.systemMsg}>{item.data.text}</div>
          ) : (
            <div
              key={item.data.id}
              style={s.msgRow(hoveredMsgId === item.data.id)}
              onMouseEnter={() => setHoveredMsgId(item.data.id)}
              onMouseLeave={() => setHoveredMsgId(null)}
            >
              <div style={s.avatar(item.data.user_id)}>
                {initials(getUsername(item.data.user_id))}
              </div>
              <div style={s.msgBody}>
                <div style={s.msgMeta}>
                  <span style={s.msgUser(item.data.user_id)}>
                    {getUsername(item.data.user_id)}
                  </span>
                  <span style={s.msgTime}>{formatTime(item.data.created_at)}</span>
                </div>
                <div style={s.msgContent}>{item.data.content}</div>
              </div>
              {item.data.user_id === auth.user_id && hoveredMsgId === item.data.id && (
                <button style={s.deleteBtn} onClick={() => handleDelete(item.data.id)}>
                  Delete
                </button>
              )}
            </div>
          )
        )}
        <div ref={bottomRef} />
      </div>

      <div style={s.inputArea}>
        <form onSubmit={send}>
          <div style={s.inputRow}>
            <textarea
              style={s.input}
              placeholder={`Message #${channelName}`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
            />
            <button type="submit" style={s.sendBtn} disabled={!text.trim() || sending}>
              Send
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
