import os
from flask import Flask, jsonify, request, g
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import messages as msg_service
import channels as ch_service
from auth import require_auth


def create_app(config: dict | None = None, engine=None):
    app = Flask(__name__)

    if config:
        app.config.update(config)

    if engine is None:
        db_url = app.config.get("DATABASE_URL") or os.getenv(
            "DATABASE_URL", "postgresql://localhost/realtime_hub"
        )
        engine = create_engine(db_url)

    app.db_engine = engine
    app.SessionFactory = sessionmaker(bind=engine, autocommit=False, autoflush=False)

    @app.before_request
    def open_db():
        g.db = app.SessionFactory()

    @app.teardown_request
    def close_db(exc):
        db = g.pop("db", None)
        if db:
            if exc:
                db.rollback()
            db.close()

    # ------------------------------------------------------------------ routes

    @app.post("/channels/<int:channel_id>/messages")
    @require_auth
    def post_message(channel_id):
        body = request.get_json(silent=True) or {}
        try:
            msg = msg_service.post_message(g.db, g.current_user_id, channel_id, body.get("content", ""))
        except ValueError as e:
            return jsonify({"error": str(e)}), 422
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        return jsonify(_serialize(msg)), 201

    @app.get("/channels/<int:channel_id>/messages")
    @require_auth
    def get_messages(channel_id):
        if not ch_service.is_member(g.db, g.current_user_id, channel_id):
            return jsonify({"error": "not a channel member"}), 403
        limit = min(int(request.args.get("limit", 50)), 100)
        offset = int(request.args.get("offset", 0))
        order = request.args.get("order", "asc")
        msgs = msg_service.get_messages(g.db, channel_id, limit=limit, offset=offset, order=order)
        return jsonify([_serialize(m) for m in msgs])

    @app.get("/messages/<int:message_id>")
    @require_auth
    def get_message(message_id):
        msg = msg_service.get_message(g.db, message_id)
        if not msg:
            return jsonify({"error": "message not found"}), 404
        if not ch_service.is_member(g.db, g.current_user_id, msg.channel_id):
            return jsonify({"error": "not a channel member"}), 403
        return jsonify(_serialize(msg))

    @app.delete("/messages/<int:message_id>")
    @require_auth
    def delete_message(message_id):
        try:
            msg_service.delete_message(g.db, message_id, g.current_user_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 404
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403
        return "", 204

    return app


def _serialize(msg: object) -> dict:
    return {
        "id": msg.id,
        "channel_id": msg.channel_id,
        "user_id": msg.user_id,
        "content": msg.content,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "updated_at": msg.updated_at.isoformat() if msg.updated_at else None,
    }


if __name__ == "__main__":
    from models import Base
    from database import engine as default_engine
    Base.metadata.create_all(default_engine)
    create_app().run(debug=True)
