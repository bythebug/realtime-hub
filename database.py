import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/realtime_hub")


class _LazySessionFactory:
    """Defers engine creation until the first call.

    This prevents importing this module from requiring the database driver
    (e.g. psycopg2) to be installed just to run tests that never touch the
    default PostgreSQL connection.
    """
    _factory = None

    def __call__(self):
        if self._factory is None:
            engine = create_engine(DATABASE_URL)
            self._factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
        return self._factory()


SessionLocal = _LazySessionFactory()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
