import os
from sqlalchemy import create_engine
from models import Base
from api.app import create_app

if __name__ == "__main__":
    db_url = os.getenv("DATABASE_URL", "postgresql://localhost/realtime_hub")
    db_url = db_url.replace("postgres://", "postgresql://", 1)
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    app = create_app(engine=engine)
    port = int(os.getenv("PORT", 5000))
    app.socketio.run(app, host="0.0.0.0", port=port, debug=False)
