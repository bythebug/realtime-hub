# Study Guide — realtime-hub

A complete reference covering every technical concept used to build this system, from database design to production deployment.

---

## Table of Contents

1. [Database Design](#1-database-design)
2. [Many-to-Many Relationships & Transactions](#2-many-to-many-relationships--transactions)
3. [Pagination, Message Ordering & Soft Deletes](#3-pagination-message-ordering--soft-deletes)
4. [Redis Pub/Sub & WebSockets](#4-redis-pubsub--websockets)
5. [Background Job Processing & Celery](#5-background-job-processing--celery)
6. [Resilience: Circuit Breakers & Graceful Degradation](#6-resilience-circuit-breakers--graceful-degradation)
7. [Monitoring, Load Testing & Metrics](#7-monitoring-load-testing--metrics)
8. [Deployment: Docker, CI/CD & Auto-Scaling](#8-deployment-docker-cicd--auto-scaling)

---

## 1. Database Design

### Normalization vs Denormalization

**Normalization** removes redundancy — each fact lives in exactly one place.
**Denormalization** copies data to avoid expensive joins at read time.

Start normalized. Denormalize only after measuring — a missing index often fixes the problem for free.

### Index Strategy

| Case | Index |
|---|---|
| Foreign key columns | Always — without them, joins and cascades do full scans |
| `WHERE` filter columns | `is_read`, `action`, `username` |
| `ORDER BY` columns | `created_at DESC` — include the direction |
| Composite queries | `(channel_id, created_at DESC)` for "latest N messages in channel" |
| JSON fields | GIN index on JSONB for `data @> '{"key": "val"}'` queries |

**Composite index column order:** put the equality column first, range/sort column second.

```sql
-- Good: equality on channel_id, range on created_at
CREATE INDEX ON messages (channel_id, created_at DESC);
```

### Event Logging (Audit Trail)

An event log records *what happened* rather than *current state*. Rows are inserted and never updated or deleted.

- `data JSONB` — flexible payload; schema varies per action
- GIN index on `data` enables `@>` (contains) queries
- Plan for archival: partition by `created_at` before the table becomes large

---

## 2. Many-to-Many Relationships & Transactions

### Join Table Pattern

```
users ──< user_channels >── channels
```

The join table holds two foreign keys and a `UNIQUE` constraint on the pair. This prevents duplicates and can carry relationship metadata (`joined_at`, `role`).

```sql
CREATE TABLE user_channels (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    joined_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_channel UNIQUE (user_id, channel_id)
);
```

Always put a `UNIQUE` constraint — without it, duplicate rows silently accumulate.

### Transaction Handling

SQLAlchemy's `Session` manages transactions:

```python
session.add(obj)    # stage in memory
session.commit()    # atomic write to DB
session.rollback()  # discard all staged changes
session.close()     # return connection to pool
```

**Double guard on duplicates:**
1. Application-level check (`is_member`) — fast, catches common case
2. DB `UNIQUE` constraint — catches concurrent races where two requests pass the app check simultaneously

```python
def join_channel(db, user_id, channel_id):
    if is_member(db, user_id, channel_id):          # app guard
        raise ValueError("already a member")
    db.add(UserChannel(user_id=user_id, channel_id=channel_id))
    db.commit()  # raises IntegrityError if race condition
```

---

## 3. Pagination, Message Ordering & Soft Deletes

### Offset Pagination

```sql
SELECT * FROM messages WHERE channel_id = ?
ORDER BY created_at ASC LIMIT 50 OFFSET 100;
```

**Pros:** simple, supports random page access.
**Cons:** drift on inserts/deletes between page fetches; slow at high offsets (DB scans and discards).

### Cursor Pagination (Keyset)

```sql
SELECT * FROM messages
WHERE channel_id = ? AND (created_at, id) > ('2024-01-15', 42)
ORDER BY created_at ASC, id ASC LIMIT 50;
```

**Pros:** no drift; fast at any depth (uses the index).
**Cons:** can't jump to arbitrary pages; cursor must be opaque to the client.

Use cursor pagination for infinite-scroll/live feeds; offset for admin dashboards.

### Message Ordering

Always include `id` as a tiebreaker — `created_at` has millisecond precision and two messages can arrive in the same millisecond.

```python
q.order_by(Message.created_at.asc(), Message.id.asc())
```

### Soft Deletes

```sql
-- Instead of DELETE:
UPDATE messages SET deleted_at = NOW() WHERE id = ?;
```

Every query must filter `WHERE deleted_at IS NULL`. Use a partial index to keep it fast:

```sql
CREATE INDEX ix_messages_active ON messages (channel_id, created_at)
WHERE deleted_at IS NULL;
```

Use soft deletes for user content (recoverable, auditable). Use hard deletes for temp data or GDPR erasure requests.

---

## 4. Redis Pub/Sub & WebSockets

### Redis Pub/Sub

Fire-and-forget messaging. Publishers push to named channels; all current subscribers receive instantly. **No persistence** — if a subscriber is offline, the message is lost.

```
Publisher  →  PUBLISH channel:42 "msg"  →  Redis  →  all subscribers
```

Channel naming convention: `channel:{id}` for chat channels, `user:{id}` for direct notifications.

**Limitations:** no persistence, no acknowledgement, no filtering. Use Redis Streams or Kafka when you need guaranteed delivery.

### WebSockets

HTTP is request/response; WebSockets are persistent bidirectional connections.

```
Client ──── HTTP GET /ws (Upgrade) ───► Server
Client ◄═══════ persistent connection ════► Server
Client ◄───── server push (no request) ──── Server
```

### Socket.IO

Adds rooms, namespaces, reconnection, and transport fallback on top of WebSockets.

```python
join_room("channel:42")                      # subscribe to room
emit("new_message", data, room="channel:42") # broadcast to all in room
leave_room("channel:42")                     # unsubscribe
```

### Multi-Process Scaling with Socket.IO

Socket.IO rooms are in-process. Scale to multiple workers by using Redis as a message queue:

```python
SocketIO(app, message_queue="redis://localhost:6379")
```

Every worker publishes emits to Redis; all workers subscribe and relay to their connected clients.

### Auth in Sockets

WebSocket connections don't carry HTTP headers after upgrade. Pass JWT as a query parameter:

```
ws://host/socket.io/?token=<jwt>
```

Validate in the `connect` handler and store `{sid: user_id}` for subsequent events.

---

## 5. Background Job Processing & Celery

### Why Job Queues

Decouples slow work from the HTTP request path:

```
POST /messages → save to DB → return 201  (fast)
                     └─► enqueue notification job  (instant)

Celery worker → pick job → send notifications  (slow, can fail, can retry)
```

Jobs survive process restarts and can run on separate machines.

### Celery Architecture

| Component | Role |
|---|---|
| **Broker** | Where tasks queue up (Redis list). Producer writes, worker reads. |
| **Backend** | Where results are stored (Redis hash). Workers write, callers read. |
| **Worker** | Separate process running `celery -A jobs.celery_app worker` |
| **Task** | Decorated function. `.delay(*args)` enqueues it. |

### Idempotency

Jobs must be safe to retry — a job can fail mid-execution and be retried, or delivered more than once.

```python
def send_notification(db, user_id, message_id):
    existing = db.query(Notification).filter(...).first()
    if existing:
        return {"status": "skipped"}   # safe to call multiple times
    db.add(Notification(...))
    db.commit()
```

DB `UNIQUE(user_id, message_id)` is the final guard against duplicates even under concurrent retries.

### Exponential Backoff

```python
raise self.retry(exc=exc, countdown=2 ** self.request.retries)
# Retry delays: 1s → 2s → 4s → MaxRetriesExceededError
```

Add jitter in production to avoid thundering herd:
```python
countdown = 2 ** self.request.retries + random.uniform(0, 1)
```

---

## 6. Resilience: Circuit Breakers & Graceful Degradation

### Why Distributed Systems Fail

Any component can fail independently. Without protection, one slow service causes cascading failure: slow timeouts exhaust threads, which makes the caller slow, which exhausts its callers.

### Circuit Breaker Pattern

```
CLOSED ──[N failures]──► OPEN ──[timeout]──► HALF_OPEN
  ▲                                               │
  └──────────────[success]───────────────────────┘
```

| State | Behavior |
|---|---|
| CLOSED | Normal — count failures |
| OPEN | Fail immediately without calling the service |
| HALF_OPEN | Allow one test request through |

```python
def call(self, func, *args, **kwargs):
    if self.state == OPEN:
        raise CircuitOpenError()    # fast-fail
    try:
        result = func(*args, **kwargs)
        self._on_success()          # reset, close circuit
        return result
    except Exception as exc:
        self._on_failure(exc)       # increment, possibly open
        raise
```

### Graceful Degradation

Design non-essential I/O as optional:

```python
# Redis failure never fails the HTTP response
try:
    rc.publish_event(channel_id, "new_message", data)
except Exception:
    pass
```

| Dependency | Type | Failure behavior |
|---|---|---|
| PostgreSQL | Hard | Return 503 |
| Redis | Soft | Save to DB, clients poll |
| Celery | Soft | No background notifications |

### Health Checks

```json
GET /health
{
  "status": "degraded",
  "services": {
    "database":  {"status": "ok"},
    "redis":     {"status": "error", "detail": "Connection refused"},
    "job_queue": {"status": "ok"}
  }
}
```

Return 200 when degraded (app still serves requests); return 503 only when the database is down.

### Retry with Backoff

```python
def retry_with_backoff(func, max_retries=3, base_delay=0.5):
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as exc:
            if attempt < max_retries:
                time.sleep(base_delay * 2 ** attempt)
    raise exc
```

---

## 7. Monitoring, Load Testing & Metrics

### The Four Golden Signals (Google SRE)

| Signal | What to track |
|---|---|
| **Latency** | How long requests take (p50, p95, p99) |
| **Traffic** | Requests per second |
| **Errors** | Rate of 5xx responses |
| **Saturation** | Queue depth, CPU, connection pool usage |

### Prometheus Metrics

```python
messages_posted = Counter("realtime_hub_messages_total", "...", ["channel_id"])
message_post_latency = Histogram("realtime_hub_message_post_duration_seconds", "...")

# Instrument in the route
start = time.perf_counter()
# ... do work ...
message_post_latency.observe(time.perf_counter() - start)
messages_posted.labels(channel_id=str(channel_id)).inc()
```

**Label strategy:** use low-cardinality labels. Never label by `user_id` — it creates millions of time series.

### Structured Logging

Emit one JSON object per log line for easy aggregation:

```json
{"ts": "2024-01-15T12:00:01", "level": "INFO", "msg": "message posted",
 "channel_id": 42, "duration_ms": 12.3}
```

### Load Testing with Locust

```python
class RealtimeHubUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(4)
    def post_message(self): ...

    @task(2)
    def read_messages(self): ...
```

Key metrics to watch:
- **p95 latency** — most users experience this
- **p99 latency** — the tail; caused by GC pauses, lock contention
- **Failure rate** — should be <0.1% under normal load

### Integration Testing

Integration tests cross layer boundaries — they're the only way to catch contract mismatches between components.

```python
def test_full_message_flow():
    # HTTP POST → DB save → Socket.IO broadcast → Celery job → notification in DB
    resp = http.post("/channels/1/messages", json={"content": "hi"})
    assert resp.status_code == 201
    assert sio_client.get_received()  # Socket.IO event received
    assert db.query(Notification).count() == 1
```

---

## 8. Deployment: Docker, CI/CD & Auto-Scaling

### Docker

A Dockerfile packages the app and its dependencies into an immutable image.

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "run.py"]
```

**Best practices:**
- Pin the base image tag (`python:3.13-slim`, not `python:latest`)
- Copy `requirements.txt` before source files — layer caching skips pip install if requirements haven't changed
- Use `--no-cache-dir` to keep image size small
- Run as non-root user in production

### Docker Compose (local stack)

```yaml
services:
  app:
    build: .
    depends_on:
      db: {condition: service_healthy}
      redis: {condition: service_started}

  celery_worker:
    build: .
    command: celery -A jobs.celery_app worker

  db:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hub"]

  redis:
    image: redis:7-alpine

  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
```

The `healthcheck` on `db` prevents the app from starting before PostgreSQL is ready to accept connections.

### CI/CD Pipeline

A typical pipeline:

```
git push
    │
    ├── [CI] install deps → run pytest → check coverage
    │
    ├── [CI] docker build → push to ECR (on main branch only)
    │
    └── [CD] deploy.sh → ECS update → wait for stable
```

**Key principles:**
- Never deploy a red build
- Run migrations before deploying new app code (additive changes only in production)
- Blue/green deployment: keep old tasks running until new ones pass health checks

### Database Migrations in Production

Safe migration order:
1. Add nullable columns or new tables (no downtime)
2. Deploy new app code that writes to both old and new columns
3. Backfill existing rows
4. Add NOT NULL constraint
5. Remove old column in a later deployment

Never rename or drop a column in the same deployment as the code change that stops using it.

### Container Orchestration (AWS ECS)

ECS runs Docker containers in two modes:
- **EC2 launch type**: you manage the underlying VMs
- **Fargate launch type**: AWS manages compute; you pay per task

**Auto-scaling in ECS:**

```json
{
  "ScalableDimension": "ecs:service:DesiredCount",
  "MinCapacity": 2,
  "MaxCapacity": 20,
  "TargetTrackingScalingPolicies": [{
    "TargetValue": 70.0,
    "PredefinedMetricType": "ECSServiceAverageCPUUtilization"
  }]
}
```

Scale on CPU for compute-bound workloads; scale on custom metrics (queue depth, request latency) for I/O-bound workloads like this one.

### Scaling the Full Stack

| Component | Scale strategy |
|---|---|
| Flask app | Horizontal (add ECS tasks); stateless by design |
| Celery workers | Horizontal (separate ECS service); stateless |
| PostgreSQL | Vertical first; then read replicas for read scaling |
| Redis | Redis Cluster for pub/sub at scale; Elasticache in AWS |
| Socket.IO | Scale via Redis message queue — all nodes share rooms |

**Never scale the database first.** Most performance issues are missing indexes or N+1 queries. Fix those before scaling hardware.

### Environment Variable Management

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection (broker + pub/sub) |
| `SECRET_KEY` | JWT signing key (min 32 chars in production) |
| `AWS_REGION` | Deployment region |

In production: use AWS Secrets Manager or Parameter Store, not plain environment variables. Rotate `SECRET_KEY` requires invalidating all active tokens.

---

## Common Issues and Solutions

| Issue | Symptom | Solution |
|---|---|---|
| N+1 queries | Slow page loads, many small DB queries | Add `joinedload()` or `selectinload()` |
| Missing index | Slow queries, high DB CPU | `EXPLAIN ANALYZE` the query; add index |
| Socket.IO rooms not syncing | Messages not reaching clients on other workers | Add Redis `message_queue` to SocketIO config |
| Celery tasks not running | Jobs enqueued but never executed | Check worker is running; check broker URL |
| Circuit breaker stays open | All Redis calls fail fast | Call `redis_breaker.reset()` after Redis recovers |
| JWT expiry not handled | 401 after token expires | Add token refresh endpoint; handle 401 on client |
| SQLite in-memory test isolation | Tests interfere with each other | Use `StaticPool` so all sessions share one connection |
| Duplicate notifications | Notification created twice | DB `UNIQUE` constraint + idempotency check |
