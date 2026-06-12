import os
from functools import wraps
from flask import request, g, jsonify, current_app
import jwt

_FALLBACK_SECRET = "dev-secret-key"


def _secret() -> str:
    try:
        return current_app.config.get("SECRET_KEY") or os.getenv("SECRET_KEY", _FALLBACK_SECRET)
    except RuntimeError:
        return os.getenv("SECRET_KEY", _FALLBACK_SECRET)


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "unauthorized"}), 401
        try:
            payload = jwt.decode(header[7:], _secret(), algorithms=["HS256"])
            g.current_user_id = payload["user_id"]
        except jwt.InvalidTokenError:
            return jsonify({"error": "invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


def make_token(user_id: int, secret: str | None = None) -> str:
    return jwt.encode(
        {"user_id": user_id},
        secret or os.getenv("SECRET_KEY", _FALLBACK_SECRET),
        algorithm="HS256",
    )
