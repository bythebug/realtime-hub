import os
from sqlalchemy import create_engine
from models import Base
from api.app import create_app

if __name__ == "__main__":
    engine = create_engine(os.getenv("DATABASE_URL", "postgresql://localhost/realtime_hub"))
    Base.metadata.create_all(engine)
    app = create_app(engine=engine)
    app.socketio.run(app, host="0.0.0.0", port=5000, debug=False)
