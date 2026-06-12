from gevent import monkey
monkey.patch_all()

import os
import time
import gevent
from sqlalchemy import create_engine
from models import Base
from api.app import create_app

db_url = os.getenv("DATABASE_URL", "postgresql://localhost/realtime_hub")
db_url = db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(db_url, pool_pre_ping=True)
app = create_app(engine=engine)


def _init_db():
    for attempt in range(30):
        try:
            Base.metadata.create_all(engine)
            app.logger.info("Database tables ready")
            return
        except Exception as exc:
            if attempt == 29:
                app.logger.error(f"DB init failed after 30 attempts: {exc}")
                return
            app.logger.warning(f"DB not ready (attempt {attempt + 1}/30), retrying in 2s...")
            time.sleep(2)


gevent.spawn(_init_db)
