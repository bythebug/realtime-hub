import { useState, useEffect } from 'react'
import { getHealth } from '../api'

export default function HealthBadge() {
  const [health, setHealth] = useState(null)

  useEffect(() => {
    let active = true
    async function poll() {
      const data = await getHealth()
      if (active) setHealth(data)
    }
    poll()
    const id = setInterval(poll, 10000)
    return () => { active = false; clearInterval(id) }
  }, [])

  const ok = health?.status === 'ok'
  const color = !health ? '#80848e' : ok ? '#3ba55c' : '#ed4245'
  const label = !health ? 'checking…' : ok ? 'healthy' : 'degraded'

  return (
    <span style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color }}>
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: color, display: 'inline-block' }} />
      {label}
    </span>
  )
}
