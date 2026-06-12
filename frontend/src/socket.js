import { io } from 'socket.io-client'

let socket = null

export function connect(token) {
  if (socket) socket.disconnect()
  socket = io('/', { auth: { token }, transports: ['websocket', 'polling'] })
  return socket
}

export function disconnect() {
  if (socket) { socket.disconnect(); socket = null }
}

export function getSocket() { return socket }
