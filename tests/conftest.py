import pytest
import fakeredis
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from models import Base, Message
from users import create_user
from channels import create_channel, join_channel
from auth import make_token
from app import create_app
import redis_client


# ------------------------------------------------------------------ redis mock

@pytest.fixture(autouse=True)
def fake_redis(monkeypatch):
    monkeypatch.setattr(redis_client, "_client", fakeredis.FakeRedis(decode_responses=True))


# ------------------------------------------------------------------ unit test db

@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture
def user(db):
    return create_user(db, "alice", "alice@example.com", "secret123")


@pytest.fixture
def other_user(db):
    return create_user(db, "bob", "bob@example.com", "secret456")


@pytest.fixture
def channel(db, user):
    return create_channel(db, user.id, "general")


# ------------------------------------------------------------------ flask test app

@pytest.fixture
def flask_app():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    app = create_app(config={"TESTING": True, "REDIS_URL": ""}, engine=engine)
    yield app
    Base.metadata.drop_all(engine)


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def app_db(flask_app):
    session = flask_app.SessionFactory()
    yield session
    session.close()


@pytest.fixture
def app_user(app_db):
    return create_user(app_db, "alice", "alice@example.com", "secret123")


@pytest.fixture
def app_other_user(app_db):
    return create_user(app_db, "bob", "bob@example.com", "secret456")


@pytest.fixture
def app_channel(app_db, app_user):
    ch = create_channel(app_db, app_user.id, "general")
    join_channel(app_db, app_user.id, ch.id)
    return ch


@pytest.fixture
def auth_headers(app_user):
    return {"Authorization": f"Bearer {make_token(app_user.id)}"}


@pytest.fixture
def other_auth_headers(app_other_user):
    return {"Authorization": f"Bearer {make_token(app_other_user.id)}"}


# ------------------------------------------------------------------ app_message
# Created directly (bypassing post_message) to avoid triggering job enqueueing
# during test setup, which would attempt a real broker connection.

@pytest.fixture
def app_message(app_db, app_user, app_channel):
    msg = Message(
        channel_id=app_channel.id,
        user_id=app_user.id,
        content="test message content",
    )
    app_db.add(msg)
    app_db.commit()
    app_db.refresh(msg)
    return msg


# ------------------------------------------------------------------ celery helpers

@pytest.fixture
def celery_eager():
    """Run Celery tasks synchronously with retries; exceptions stored in result."""
    from celery_app import celery
    celery.conf.update(task_always_eager=True, task_eager_propagates=False)
    yield celery
    celery.conf.update(task_always_eager=False, task_eager_propagates=False)


@pytest.fixture
def task_db(flask_app, monkeypatch):
    """Wire Celery tasks to the test database."""
    import tasks as t
    session = flask_app.SessionFactory()
    monkeypatch.setattr(t, "_session_factory", lambda: session)
    yield session
    session.close()
