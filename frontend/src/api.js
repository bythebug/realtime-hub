const BASE = ''

async function req(method, path, body, token) {
  const res = await fetch(BASE + path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) throw new Error(data?.error || `HTTP ${res.status}`)
  return data
}

export const login = (email, password) =>
  req('POST', '/auth/login', { email, password })

export const register = (username, email, password) =>
  req('POST', '/auth/register', { username, email, password })

export const getMyChannels = (token) =>
  req('GET', '/channels/me', null, token)

export const getAllChannels = (token) =>
  req('GET', '/channels', null, token)

export const createChannel = (token, name) =>
  req('POST', '/channels', { name }, token)

export const joinChannel = (token, channelId) =>
  req('POST', `/channels/${channelId}/join`, {}, token)

export const leaveChannel = (token, channelId) =>
  req('DELETE', `/channels/${channelId}/leave`, null, token)

export const deleteChannel = (token, channelId) =>
  req('DELETE', `/channels/${channelId}`, null, token)

export const getMessages = (token, channelId, { limit = 50, offset = 0 } = {}) =>
  req('GET', `/channels/${channelId}/messages?limit=${limit}&offset=${offset}&order=desc`, null, token)

export const deleteMessage = (token, messageId) =>
  req('DELETE', `/messages/${messageId}`, null, token)

export const getUser = (token, userId) =>
  req('GET', `/users/${userId}`, null, token)

export const getNotifications = (token) =>
  req('GET', '/notifications', null, token)

export const markAllNotificationsRead = (token) =>
  req('POST', '/notifications/read-all', {}, token)

export const getHealth = () =>
  fetch(BASE + '/health').then((r) => r.json()).catch(() => ({ status: 'unknown' }))
