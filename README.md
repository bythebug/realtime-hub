# realtime-hub

A production-grade real-time notification system built with Flask, Socket.IO, Redis, Celery, and PostgreSQL.

## Architecture

```
Client (Browser / Mobile / API)
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
| Resilience | Circuit breaker, retry with backoff |
| Observability | Prometheus metrics, structured JSON logging |
| Testing | pytest (67 tests: unit, integration, resilience) |
| Load testing | Locust |

---

## Quick Start (Docker)

```bash
# Clone and start everything
git clone https://github.com/bythebug/realtime-hub.git
cd realtime-hub

cp .env.example .env          # fill in secrets
docker-compose up --build
```

Services:
- App: http://localhost:5000
- Prometheus: http://localhost:9090
- PostgreSQL: localhost:5432
- Redis: localhost:6379

---

## Running Locally (without Docker)

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Start dependencies
docker-compose up db redis -d

# Set env vars
export DATABASE_URL=postgresql://hub:hub@localhost:5432/realtime_hub
export REDIS_URL=redis://localhost:6379/0
export SECRET_KEY=your-secret-key

# Run the app
python run.py

# Run the Celery worker (separate terminal)
celery -A jobs.celery_app worker --loglevel=info

# Run tests
pytest tests/
```

---

## API Reference

### Auth

| Method | Endpoint | Auth | Body | Description |
|--------|----------|------|------|-------------|
| `POST` | `/auth/register` | — | `{username, email, password}` | Register + get JWT |

### Channels

| Method | Endpoint | Auth | Body | Description |
|--------|----------|------|------|-------------|
| `POST` | `/channels` | ✓ | `{name}` | Create channel (auto-joins creator) |

### Messages

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/channels/{id}/messages` | ✓ | Post a message |
| `GET`  | `/channels/{id}/messages` | ✓ | Fetch message history (paginated) |
| `GET`  | `/messages/{id}` | ✓ | Fetch a single message |
| `DELETE` | `/messages/{id}` | ✓ | Soft-delete a message (author only) |

**Query params for GET messages:**

| Param | Default | Description |
|-------|---------|-------------|
| `limit` | `50` | Max messages (capped at 100) |
| `offset` | `0` | Pagination offset |
| `order` | `asc` | `asc` (oldest first) or `desc` (newest first) |

**Auth header:** `Authorization: Bearer <token>`

### Observability

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health (200 OK / 503 if DB down) |
| `GET` | `/health/circuit-breakers` | Circuit breaker states |
| `GET` | `/metrics` | Prometheus metrics |

---

## WebSocket Events

Connect with `?token=<jwt>` query parameter.

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
| `error` | `{message}` | Error (e.g. not a member) |

---

## Configuration

Copy `.env.example` to `.env` and fill in values:

```bash
cp .env.example .env
```

See [.env.example](.env.example) for all required variables.

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

**Test counts:** 67 tests across 6 suites (unit, integration, resilience).

### Load Testing

```bash
# Start the app first, then:
locust -f load_test.py --headless -u 100 -r 10 -t 60s --host http://localhost:5000
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

For detailed system design and scaling decisions, see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Project Structure

```
realtime-hub/
├── models.py          # SQLAlchemy models
├── database.py        # DB engine / session factory
├── schema.sql         # DDL with indexes
├── run.py             # App entry point
│
├── api/               # Flask app, routes, auth, WebSocket
│   ├── app.py
│   ├── auth.py
│   ├── error_handlers.py
│   └── websocket.py
│
├── services/          # Business logic (no Flask/Celery dependency)
│   ├── channels.py
│   ├── messages.py
│   └── users.py
│
├── jobs/              # Async task processing
│   ├── celery_app.py
│   ├── tasks.py
│   └── job_queue.py
│
├── infra/             # External service wrappers
│   ├── redis_client.py
│   ├── circuit_breaker.py
│   └── monitoring.py
│
├── tests/             # 67 tests
├── docker-compose.yml
├── Dockerfile
├── prometheus.yml
└── load_test.py
```
