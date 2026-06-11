import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from models import Base
from users import create_user
from channels import create_channel, join_channel
from auth import make_token
from app import create_app


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
# StaticPool ensures all sessions share the same in-memory database, which is
# required so data written by app_db fixtures is visible inside Flask requests.

@pytest.fixture
def flask_app():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    app = create_app(engine=engine)
    app.config["TESTING"] = True
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
