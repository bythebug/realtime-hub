# realtime-hub

A real-time event system built with Flask, Socket.IO, Redis, Celery, and PostgreSQL. Events are published, fanned out via Redis pub/sub, and delivered to connected clients over WebSocket — with a React frontend as the demo interface.

## Architecture

```
Client (Browser)
        │
        ├── HTTP/REST ────────────────────────────────────┐
        └── WebSocket (Socket.IO) ───────────────────┐    │
                                                     │    │
                              ┌──────────────────────▼────▼──┐
                              │           api/                │
                              │  Flask · Auth · Routes · WS   │
                              └──────────────┬────────────────┘
                                             │
              ┌──────────────────────────────┼──────────────────────────┐
              │                              │                           │
          services/                       jobs/                      infra/
    ┌──────────────────┐          ┌──────────────────┐        ┌──────────────────┐
    │ channels.py      │          │ celery_app.py     │        │ redis_client.py  │
    │ messages.py      │          │ tasks.py          │        │ monitoring.py    │
    │ users.py         │          │ job_queue.py      │        │ circuit_breaker  │
    └────────┬─────────┘          └────────┬──────────┘        └────────┬─────────┘
             │                             │                             │
             └─────────────────────────────┴─────────────────────────────┘
                                           │
                             ┌─────────────▼──────────────┐
                             │         Data Layer          │
                             │   PostgreSQL  ·  Redis      │
                             └─────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| API | Flask 3, Flask-SocketIO |
| Auth | JWT (PyJWT) |
| Real-time | Socket.IO, Redis pub/sub |
| Database | PostgreSQL (SQLAlchemy ORM) |
| Job queue | Celery 5 + Redis broker |
| Frontend | React 18, Vite |
| Resilience | Circuit breaker, retry with backoff |
| Observability | Prometheus metrics, structured JSON logging |
| Testing | pytest (67 tests: unit, integration, resilience) |
| Load testing | Locust |

---

## Quick Start (Docker)

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
git clone https://github.com/bythebug/realtime-hub.git
cd realtime-hub
docker compose up --build
```

Services:

| Service | URL |
|---|---|
| App | http://localhost:5001 |
| Prometheus | http://localhost:9090 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

> **Note:** Port 5001 is used for the app because macOS reserves 5000 for AirPlay Receiver.

---

## Running Locally (without Docker)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Start dependencies
docker compose up db redis -d

# Set env vars
export DATABASE_URL=postgresql://hub:hub@localhost:5432/realtime_hub
export REDIS_URL=redis://localhost:6379/0
export SECRET_KEY=your-secret-key

# Run the app
python run.py

# Run the Celery worker (separate terminal)
celery -A jobs.celery_app worker --loglevel=info
```

---

## Demo Account

On first startup, demo data is seeded automatically — no extra steps needed. The stack creates 4 users and 4 channels (`#general`, `#engineering`, `#random`, `#announcements`) with sample conversations.

Default demo account:

| Field | Value |
|---|---|
| Email | `demo@realtimehub.app` |
| Password | `demo1234` |

If starting fresh (empty DB), you can also create the demo account manually:

```bash
curl -s -X POST http://localhost:5001/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "demo", "email": "demo@realtimehub.app", "password": "demo1234"}'
```

---

## Frontend

The React frontend is served by the Flask app at `/` in production (built into `frontend/dist` during the Docker build). In development, run the Vite dev server separately:

```bash
cd frontend
npm install
npm run dev       # http://localhost:5173
```

**Features:**
- Register / sign in
- Create channels, join/leave channels
- Real-time messaging via WebSocket
- Usernames resolved and cached client-side
- Message history with pagination (load earlier messages)
- Delete your own messages (hover to reveal)
- Notification bell with unread count — live updates via WebSocket, click to navigate to channel
- Delete channel (creator only, with confirmation)
- Live health indicator

---

## API Reference

All protected endpoints require `Authorization: Bearer <token>`.

### Auth

| Method | Endpoint | Auth | Body | Description |
|--------|----------|------|------|-------------|
| `POST` | `/auth/register` | — | `{username, email, password}` | Register and receive JWT |
| `POST` | `/auth/login` | — | `{email, password}` | Login and receive JWT |

### Users

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/users/{id}` | ✓ | Get a user's public profile (`id`, `username`) |

### Channels

| Method | Endpoint | Auth | Body | Description |
|--------|----------|------|------|-------------|
| `GET` | `/channels` | ✓ | — | List all channels |
| `GET` | `/channels/me` | ✓ | — | List channels you've joined |
| `POST` | `/channels` | ✓ | `{name}` | Create a channel (auto-joins creator) |
| `POST` | `/channels/{id}/join` | ✓ | — | Join a channel |
| `DELETE` | `/channels/{id}/leave` | ✓ | — | Leave a channel |
| `DELETE` | `/channels/{id}` | ✓ | — | Delete a channel (creator only) |

### Messages

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/channels/{id}/messages` | ✓ | Post a message |
| `GET` | `/channels/{id}/messages` | ✓ | Fetch message history (paginated) |
| `GET` | `/messages/{id}` | ✓ | Fetch a single message |
| `DELETE` | `/messages/{id}` | ✓ | Delete a message (author only) |

**Query params for GET messages:**

| Param | Default | Description |
|-------|---------|-------------|
| `limit` | `50` | Max messages returned (capped at 100) |
| `offset` | `0` | Pagination offset |
| `order` | `desc` | `asc` (oldest first) or `desc` (newest first) |

### Notifications

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/notifications` | ✓ | Fetch unread notifications (newest 50) |
| `POST` | `/notifications/read-all` | ✓ | Mark all unread notifications as read |

Each notification includes `message_id` and `channel_id` for client-side navigation.

### Observability

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health (200 OK / 503 if DB down) |
| `GET` | `/health/circuit-breakers` | Circuit breaker states |
| `GET` | `/metrics` | Prometheus metrics |

---

## WebSocket Events

Connect with `?token=<jwt>` or pass token in the `auth` object.

On connect, the client is automatically joined to a personal `user:{id}` room for direct notifications.

### Client → Server

| Event | Payload | Description |
|-------|---------|-------------|
| `join` | `{channel_id}` | Join a channel room |
| `message` | `{channel_id, content}` | Send a message |
| `leave` | `{channel_id}` | Leave a channel room |

### Server → Client

| Event | Payload | Description |
|-------|---------|-------------|
| `new_message` | `{id, channel_id, user_id, content, created_at}` | New message in joined channel |
| `user_joined` | `{user_id, channel_id}` | User joined the channel |
| `user_left` | `{user_id, channel_id}` | User left the channel |
| `notification` | `{notification_id, message_id}` | New notification for this user (personal room) |
| `error` | `{message}` | Error (e.g. not a channel member) |

---

## Event Audit Log

Key user actions are recorded asynchronously to the `events` table via Celery:

| Action | Trigger |
|---|---|
| `user.registered` | POST /auth/register |
| `user.login` | POST /auth/login |
| `message.posted` | POST /channels/:id/messages |
| `channel.joined` | POST /channels/:id/join |
| `channel.left` | DELETE /channels/:id/leave |
| `channel.deleted` | DELETE /channels/:id |

All event logging is fire-and-forget — a logging failure never affects the HTTP response.

---

## Testing

```bash
# All tests
pytest tests/ -v

# By suite
pytest tests/test_channels.py
pytest tests/test_messages.py
pytest tests/test_realtime.py
pytest tests/test_jobs.py
pytest tests/test_resilience.py
pytest tests/test_integration.py
```

67 tests across 6 suites (unit, integration, resilience).

### Load Testing

```bash
locust -f load_test.py --headless -u 100 -r 10 -t 60s --host http://localhost:5001
```

---

## Deployment

See [deploy.sh](deploy.sh) for a complete AWS ECR + ECS deployment script.

```bash
export AWS_REGION=us-east-1
export ECR_REGISTRY=<account-id>.dkr.ecr.us-east-1.amazonaws.com
export ECS_CLUSTER=realtime-hub-cluster
export ECS_SERVICE=realtime-hub-service

./deploy.sh
```

For system design and scaling decisions, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Project Structure

```
realtime-hub/
├── models.py              # SQLAlchemy models
├── database.py            # DB engine / session factory
├── schema.sql             # DDL with indexes
├── run.py                 # App entry point
│
├── api/                   # Flask app, routes, auth, WebSocket
│   ├── app.py
│   ├── auth.py
│   ├── error_handlers.py
│   └── websocket.py
│
├── services/              # Business logic (no Flask/Celery dependency)
│   ├── channels.py
│   ├── messages.py
│   └── users.py
│
├── jobs/                  # Async task processing
│   ├── celery_app.py
│   ├── tasks.py
│   └── job_queue.py
│
├── infra/                 # External service wrappers
│   ├── redis_client.py
│   ├── circuit_breaker.py
│   └── monitoring.py
│
├── frontend/              # React + Vite frontend
│   └── src/
│       ├── components/
│       ├── api.js
│       └── socket.js
│
├── tests/                 # 67 tests
├── ARCHITECTURE.md        # System design and scaling decisions
├── docker-compose.yml
├── Dockerfile
├── prometheus.yml
└── load_test.py
```
