import os
import jwt
from flask import request
from flask_socketio import join_room, leave_room, emit
from services.channels import is_member
from services.messages import post_message
from infra import redis_client as rc


def register_handlers(socketio, session_factory):
    """Attach all Socket.IO event handlers to the given SocketIO instance.

    session_factory is called to create a new DB session for each handler
    because Flask's g/before_request lifecycle does not fire for socket events.
    """
    _connected: dict[str, int] = {}

    def _current_user() -> int | None:
        return _connected.get(request.sid)

    def _secret() -> str:
        return os.getenv("SECRET_KEY", "dev-secret-key")

    @socketio.on("connect")
    def on_connect(auth):
        token = request.args.get("token", "") or (auth or {}).get("token", "")
        if not token:
            return False
        try:
            payload = jwt.decode(token, _secret(), algorithms=["HS256"])
            user_id = payload["user_id"]
            _connected[request.sid] = user_id
            join_room(f"user:{user_id}")
        except jwt.InvalidTokenError:
            return False

    @socketio.on("disconnect")
    def on_disconnect():
        _connected.pop(request.sid, None)

    @socketio.on("join")
    def on_join(data):
        user_id = _current_user()
        channel_id = (data or {}).get("channel_id")
        if not user_id or not channel_id:
            return

        db = session_factory()
        try:
            if not is_member(db, user_id, channel_id):
                emit("error", {"message": "not a channel member"})
                return
        finally:
            db.close()

        join_room(f"channel:{channel_id}")
        emit(
            "user_joined",
            {"user_id": user_id, "channel_id": channel_id},
            room=f"channel:{channel_id}",
        )

    @socketio.on("message")
    def on_message(data):
        user_id = _current_user()
        channel_id = (data or {}).get("channel_id")
        content = (data or {}).get("content", "")
        if not user_id or not channel_id:
            return

        db = session_factory()
        try:
            try:
                msg = post_message(db, user_id, channel_id, content)
            except (ValueError, PermissionError) as e:
                emit("error", {"message": str(e)})
                return

            event_data = {
                "id": msg.id,
                "channel_id": msg.channel_id,
                "user_id": msg.user_id,
                "content": msg.content,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }
        finally:
            db.close()

        try:
            rc.publish_event(channel_id, "new_message", event_data)
        except Exception:
            pass

        emit("new_message", event_data, room=f"channel:{channel_id}")

    @socketio.on("leave")
    def on_leave(data):
        user_id = _current_user()
        channel_id = (data or {}).get("channel_id")
        if not user_id or not channel_id:
            return
        leave_room(f"channel:{channel_id}")
        emit(
            "user_left",
            {"user_id": user_id, "channel_id": channel_id},
            room=f"channel:{channel_id}",
            include_self=False,
        )
