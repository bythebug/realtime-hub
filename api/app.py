import os
import time
from flask import Flask, jsonify, request, g, current_app, Response
from flask_socketio import SocketIO
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from services import messages as msg_service
from services import channels as ch_service
from infra import redis_client as rc
from api.auth import require_auth, make_token
from api.websocket import register_handlers
from api.error_handlers import register_error_handlers
from infra.monitoring import (
    get_health_status,
    start_health_logging,
    get_prometheus_metrics,
    record_message_posted,
)
from infra.circuit_breaker import redis_breaker, db_breaker


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

    redis_url = (
        app.config.get("REDIS_URL")
        if "REDIS_URL" in (config or {})
        else os.getenv("REDIS_URL", "")
    )
    socketio = SocketIO(
        app,
        message_queue=redis_url or None,
        cors_allowed_origins="*",
        async_mode="threading",
    )
    app.socketio = socketio
    register_handlers(socketio, app.SessionFactory)
    register_error_handlers(app)

    # ------------------------------------------------------------------ db lifecycle

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

    # ------------------------------------------------------------------ auth

    @app.post("/auth/register")
    def register():
        body = request.get_json(silent=True) or {}
        try:
            from services.users import create_user
            user = create_user(
                g.db,
                body.get("username", ""),
                body.get("email", ""),
                body.get("password", ""),
            )
        except Exception as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"token": make_token(user.id), "user_id": user.id}), 201

    # ------------------------------------------------------------------ channels

    @app.post("/channels")
    @require_auth
    def create_channel():
        body = request.get_json(silent=True) or {}
        name = body.get("name", "").strip()
        if not name:
            return jsonify({"error": "name required"}), 422
        try:
            ch = ch_service.create_channel(g.db, g.current_user_id, name)
            ch_service.join_channel(g.db, g.current_user_id, ch.id)
        except Exception as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"id": ch.id, "name": ch.name}), 201

    # ------------------------------------------------------------------ messages

    @app.post("/channels/<int:channel_id>/messages")
    @require_auth
    def post_message(channel_id):
        start = time.perf_counter()
        body = request.get_json(silent=True) or {}
        try:
            msg = msg_service.post_message(g.db, g.current_user_id, channel_id, body.get("content", ""))
        except ValueError as e:
            return jsonify({"error": str(e)}), 422
        except PermissionError as e:
            return jsonify({"error": str(e)}), 403

        serialized = _serialize(msg)
        record_message_posted(channel_id, time.perf_counter() - start)

        try:
            current_app.socketio.emit("new_message", serialized, room=f"channel:{channel_id}")
        except Exception:
            pass

        try:
            rc.publish_event(channel_id, "new_message", serialized)
        except Exception:
            pass

        return jsonify(serialized), 201

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

    # ------------------------------------------------------------------ observability

    @app.get("/health")
    def health():
        status = get_health_status(g.db)
        http_code = 503 if status["services"]["database"]["status"] != "ok" else 200
        return jsonify(status), http_code

    @app.get("/health/circuit-breakers")
    def health_circuit_breakers():
        return jsonify({
            "redis":    redis_breaker.as_dict(),
            "database": db_breaker.as_dict(),
        })

    @app.get("/metrics")
    def metrics():
        body, content_type = get_prometheus_metrics()
        return Response(body, status=200, mimetype=content_type)

    if not app.config.get("TESTING"):
        start_health_logging(app)

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
