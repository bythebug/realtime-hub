import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
from users import create_user
from channels import create_channel


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
