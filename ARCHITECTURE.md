# Architecture

## System Overview

realtime-hub is a horizontally scalable real-time messaging backend. It separates concerns into four distinct layers:

| Package | Responsibility | Dependencies |
|---------|---------------|--------------|
| `api/` | HTTP routing, WebSocket events, auth | services/, infra/ |
| `services/` | Business logic, validation, DB queries | models, database |
| `jobs/` | Async notification delivery, event logging | services/, infra/ |
| `infra/` | Redis pub/sub, metrics, circuit breakers | external services |

`services/` has no knowledge of Flask or Celery — it is plain Python, independently testable.

---

## Data Flow: Posting a Message

```
POST /channels/42/messages
  {"content": "hello"}
        │
        ▼
[1] api/app.py — require_auth decorator validates JWT
        │
        ▼
[2] services/messages.py — post_message()
        ├── validate content (length, not empty)
        ├── check is_member(user, channel)
        ├── INSERT message → PostgreSQL
        └── _enqueue_member_notifications() ──► [fire-and-forget]
                                                      │
        ┌─────────────────────────────────────────────┘
        │
        ▼
[3] api/app.py — post_message route continues
        ├── socketio.emit("new_message", ..., room="channel:42")
        │       └── all WebSocket clients in room receive it instantly
        └── redis_client.publish_event(42, "new_message", data)
                └── any Redis subscribers receive it (other consumers)
        │
        ▼
[4] Return 201 — message saved; real-time delivery is best-effort

[5] jobs/tasks.py — send_notification_job (async, Celery worker)
        ├── idempotency check: skip if notification already exists
        ├── INSERT notification → PostgreSQL
        └── record_notification("success") → Prometheus counter
```

**Key property:** Steps 3–5 are non-fatal. If Redis or Celery is down, the message is still saved and 201 is returned. Users fall back to polling.

---

## Data Flow: Real-Time Connection

```
Client connects to ws://host/socket.io?token=<jwt>
        │
        ▼
[1] api/websocket.py — on_connect()
        ├── decode JWT → extract user_id
        ├── store {sid: user_id} in memory
        └── reject (return False) if invalid

Client emits: join {"channel_id": 42}
        │
        ▼
[2] on_join()
        ├── look up user_id from sid
        ├── DB check: is_member(user_id, 42)
        ├── join_room("channel:42")   ← Socket.IO room
        └── emit "user_joined" to room

Client emits: message {"channel_id": 42, "content": "hi"}
        │
        ▼
[3] on_message()
        ├── post_message() → saves to DB + enqueues notification
        └── emit "new_message" to room "channel:42"
              └── all clients in room receive it
```

---

## Data Flow: Notification Job

```
Celery worker (separate process)
        │
        ▼
[1] Pick job from Redis queue (broker)
        │
        ▼
[2] jobs/tasks.py — send_notification_job(user_id, message_id)
        ├── open DB session (own connection, not Flask g)
        ├── idempotency: SELECT existing notification
        │       └── if exists → return "skipped"
        ├── INSERT Notification(user_id, message_id)
        ├── commit
        └── record_notification("success")

On failure:
        └── self.retry(countdown=2^n)  ← exponential backoff
                ├── attempt 1: retry in 1s
                ├── attempt 2: retry in 2s
                ├── attempt 3: retry in 4s
                └── attempt 4: MaxRetriesExceededError → FAILURE state
```

---

## Database Schema

```
users ──────────────────────────────────────────────────────┐
  id, username, email, password_hash, created_at             │
                                                             │
channels ────────────────────────┐                           │
  id, name, creator_id ──────────┘ (FK → users)              │
  created_at                                                 │
                                                             │
user_channels (join table)                                   │
  id, user_id ──────────────────────────────────────────────┘
  channel_id ──────────────────────────────────────────────┐
  joined_at                                                 │
  UNIQUE(user_id, channel_id)                               │
                                                            │
messages ───────────────────────────────────────────────────┘
  id, channel_id, user_id (both FK)
  content, created_at, updated_at, deleted_at (soft delete)
  INDEX(channel_id, created_at DESC)  ← hot query path

notifications
  id, user_id, message_id, is_read, created_at
  UNIQUE(user_id, message_id)  ← idempotency constraint
  INDEX(user_id, is_read)      ← "unread for user" query

events (append-only audit log)
  id, user_id, action, data (JSONB), created_at
  GIN INDEX(data)              ← JSON payload queries
```

---

## Resilience Design

### Circuit Breaker (infra/circuit_breaker.py)

```
CLOSED ──[5 failures]──► OPEN ──[30s timeout]──► HALF_OPEN
  ▲                                                    │
  └─────────────[success]──────────────────────────────┘
```

- `redis_breaker`: threshold=5, recovery=30s — wraps all Redis publish calls
- `db_breaker`: threshold=3, recovery=60s — available for DB health checks

### Graceful Degradation

| Service Down | Impact | Fallback |
|---|---|---|
| Redis | No real-time push, no pub/sub | Messages saved; clients poll |
| Celery | No background notifications | Notifications queued when worker recovers |
| Monitoring | No metrics | App continues serving |
| PostgreSQL | App cannot serve requests | Returns 503 |

---

## Scaling Considerations

### Horizontal scaling (multiple app instances)

Socket.IO rooms are in-process. To broadcast across instances, configure the Redis message queue:

```python
# api/app.py — already configured
SocketIO(app, message_queue="redis://...", ...)
```

Every instance subscribes to the same Redis channel. An emit on instance A reaches clients connected to instance B.

### Database connection pooling

Each Flask request opens one session (`before_request`) and closes it (`teardown_request`). With 10 workers × 10 threads, configure PostgreSQL `max_connections` and use PgBouncer to pool:

```
App workers → PgBouncer (pool 20) → PostgreSQL (max_connections=100)
```

### Celery worker scaling

Workers are stateless. Scale horizontally:

```bash
celery -A jobs.celery_app worker --concurrency=8 --autoscale=16,4
```

Add more worker containers in ECS/Kubernetes independently of app containers.

### Redis

Use Redis Cluster for pub/sub at scale. Separate broker DB and cache DB:

```
REDIS_URL=redis://host:6379/0        # Celery broker
REDIS_CACHE_URL=redis://host:6379/1  # Session / rate limiting
```

### Read scaling

Add read replicas for the `GET /channels/{id}/messages` hot path. Route read queries to replicas, writes to primary.

---

## Observability

| Signal | Tool | Endpoint / Location |
|---|---|---|
| Metrics | Prometheus + prometheus_client | `GET /metrics` |
| Health | Custom | `GET /health` |
| Structured logs | JSONFormatter | stdout (ingested by CloudWatch / Datadog) |
| Circuit state | Custom | `GET /health/circuit-breakers` |

Key metrics:
- `realtime_hub_messages_total{channel_id}` — throughput per channel
- `realtime_hub_message_post_duration_seconds` — p95/p99 latency histogram
- `realtime_hub_notifications_total{status}` — notification pipeline health
