"""Seed demo data on first startup. Skips if data already exists."""
import logging
from models import User, Channel, UserChannel, Message
from services.users import create_user
from services.channels import create_channel, join_channel
from services.messages import post_message

logger = logging.getLogger(__name__)

USERS = [
    ("demo",  "demo@realtimehub.app", "demo1234"),
    ("alice", "alice@example.com",    "pass1234"),
    ("bob",   "bob@example.com",      "pass1234"),
    ("carol", "carol@example.com",    "pass1234"),
]

SEED = [
    ("general", [
        ("alice", "Hey everyone, welcome to realtime-hub!"),
        ("bob",   "Thanks! Glad to be here."),
        ("carol", "This real-time stuff is pretty cool."),
        ("demo",  "Agreed — open it in two tabs and watch messages appear instantly."),
        ("alice", "Just tried it. Works great!"),
        ("bob",   "What stack is this built on?"),
        ("demo",  "Flask + Socket.IO on the backend, React + Vite on the frontend, Postgres + Redis underneath."),
        ("carol", "Nice. Does it scale?"),
        ("demo",  "Redis pub/sub fans out WebSocket events across multiple servers, so yes."),
        ("alice", "There are also circuit breakers and Prometheus metrics. Pretty production-grade for a study project."),
    ]),
    ("engineering", [
        ("demo",  "Stack overview: Python Flask API, SQLAlchemy ORM, Celery for async jobs."),
        ("bob",   "Why Celery if the app is mostly real-time?"),
        ("demo",  "Background jobs — things like notifications or cleanup tasks that shouldn't block the request."),
        ("alice", "Makes sense. What's the WebSocket transport?"),
        ("demo",  "Socket.IO with gevent async mode. Redis is the message queue between workers."),
        ("carol", "How do you handle reconnects?"),
        ("alice", "Socket.IO handles that automatically on the client side."),
        ("bob",   "Are there tests?"),
        ("demo",  "67 of them — unit, integration, and resilience tests. Run with: pytest tests/"),
        ("carol", "Solid. I'll take a look at the circuit breaker implementation."),
    ]),
    ("random", [
        ("carol", "Anyone else think the light theme looks better than the original dark one?"),
        ("bob",   "Definitely. Easier on the eyes during the day."),
        ("alice", "I'd add a theme toggle eventually."),
        ("demo",  "Good idea — the CSS variables make it easy, just swap the :root values."),
        ("carol", "Classic 'it's just a few variables' famous last words."),
        ("bob",   "Ha. Okay but it really is just variables this time."),
        ("alice", "True, I saw the index.css. Very clean."),
    ]),
    ("announcements", [
        ("alice", "Welcome to the announcements channel. This is for important updates only."),
        ("demo",  "First update: the app is live locally at http://localhost:5001"),
        ("alice", "Second: demo account is demo@realtimehub.app / demo1234"),
        ("bob",   "Third: you can create channels, join others, and messages are real-time."),
    ]),
]


def seed(db):
    if db.query(User).first():
        return  # already seeded

    logger.info("Seeding demo data...")

    users = {}
    for username, email, password in USERS:
        u = create_user(db, username, email, password)
        users[username] = u

    for channel_name, messages in SEED:
        creator = users[messages[0][0]]
        ch = create_channel(db, creator.id, channel_name)

        joined = {creator.id}
        for username, _ in messages:
            u = users[username]
            if u.id not in joined:
                join_channel(db, u.id, ch.id)
                joined.add(u.id)

        for username, content in messages:
            post_message(db, users[username].id, ch.id, content)

    logger.info("Demo data seeded — 4 users, %d channels", len(SEED))
