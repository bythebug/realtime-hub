import { useState, useEffect, useCallback } from 'react'
import { getAllChannels, getMyChannels, createChannel, joinChannel, leaveChannel } from '../api'

const s = {
  root: {
    width: 240, background: 'var(--bg-sidebar)', display: 'flex',
    flexDirection: 'column', flexShrink: 0, overflow: 'hidden',
  },
  section: { padding: '16px 8px 4px', fontSize: 11, fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: 0.8 },
  channelList: { overflowY: 'auto', flex: 1 },
  channel: (active) => ({
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '6px 8px', borderRadius: 6, margin: '1px 6px', cursor: 'pointer',
    background: active ? 'var(--bg-sidebar-active)' : 'transparent',
    color: active ? '#fff' : 'var(--text-muted)',
    fontSize: 14, fontWeight: active ? 600 : 400,
  }),
  channelName: { display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 },
  channelHash: { color: 'inherit', flexShrink: 0 },
  joinBtn: {
    padding: '2px 8px', background: 'rgba(88,101,242,0.15)', color: 'var(--accent)',
    fontSize: 11, borderRadius: 4,
  },
  leaveBtn: {
    padding: '1px 6px', background: 'rgba(214,54,56,0.1)', color: 'var(--danger)',
    fontSize: 12, borderRadius: 4, lineHeight: 1.4,
  },
  createRow: {
    padding: '12px 14px 16px', borderTop: '1px solid rgba(0,0,0,0.07)',
  },
  createInput: { width: '100%', fontSize: 13, padding: '7px 10px' },
  createBtn: {
    marginTop: 8, width: '100%', padding: '8px', background: 'var(--accent)', color: '#fff',
  },
}

export default function Sidebar({ auth, activeChannelId, onSelectChannel }) {
  const [myChannels, setMyChannels] = useState([])
  const [allChannels, setAllChannels] = useState([])
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [hoveredChannelId, setHoveredChannelId] = useState(null)

  const refresh = useCallback(async () => {
    const [mine, all] = await Promise.all([
      getMyChannels(auth.token),
      getAllChannels(auth.token),
    ])
    setMyChannels(mine)
    setAllChannels(all)
  }, [auth.token])

  useEffect(() => { refresh() }, [refresh])

  const myIds = new Set(myChannels.map((c) => c.id))
  const browseable = allChannels.filter((c) => !myIds.has(c.id))

  async function handleCreate(e) {
    e.preventDefault()
    if (!newName.trim()) return
    setCreating(true)
    try {
      await createChannel(auth.token, newName.trim())
      setNewName('')
      await refresh()
    } catch {}
    setCreating(false)
  }

  async function handleLeave(e, channelId) {
    e.stopPropagation()
    try {
      await leaveChannel(auth.token, channelId)
      if (channelId === activeChannelId) onSelectChannel(null)
      await refresh()
    } catch {}
  }

  async function handleJoin(channelId) {
    try {
      await joinChannel(auth.token, channelId)
      await refresh()
      onSelectChannel(channelId)
    } catch {}
  }

  return (
    <div style={s.root}>
      <div style={s.channelList}>
        <div style={s.section}>Your Channels</div>
        {myChannels.length === 0 && (
          <div style={{ padding: '8px 14px', color: 'var(--text-muted)', fontSize: 13 }}>No channels yet</div>
        )}
        {myChannels.map((ch) => (
          <div
            key={ch.id}
            style={s.channel(ch.id === activeChannelId)}
            onClick={() => onSelectChannel(ch.id)}
            onMouseEnter={() => setHoveredChannelId(ch.id)}
            onMouseLeave={() => setHoveredChannelId(null)}
          >
            <div style={s.channelName}>
              <span style={s.channelHash}>#</span>
              <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ch.name}</span>
            </div>
            {hoveredChannelId === ch.id && (
              <button style={s.leaveBtn} onClick={(e) => handleLeave(e, ch.id)} title="Leave channel">×</button>
            )}
          </div>
        ))}

        {browseable.length > 0 && (
          <>
            <div style={{ ...s.section, marginTop: 12 }}>Browse Channels</div>
            {browseable.map((ch) => (
              <div key={ch.id} style={s.channel(false)}>
                <div style={s.channelName}>
                  <span style={s.channelHash}>#</span>
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ch.name}</span>
                </div>
                <button style={s.joinBtn} onClick={() => handleJoin(ch.id)}>Join</button>
              </div>
            ))}
          </>
        )}
      </div>

      <div style={s.createRow}>
        <form onSubmit={handleCreate}>
          <input
            style={s.createInput}
            placeholder="New channel name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
          />
          <button type="submit" style={s.createBtn} disabled={creating || !newName.trim()}>
            {creating ? 'Creating…' : '+ Create Channel'}
          </button>
        </form>
      </div>
    </div>
  )
}
