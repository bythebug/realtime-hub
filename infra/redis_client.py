import json
import os
import redis
from infra.circuit_breaker import redis_breaker

# Lazy attribute — tests replace this via monkeypatch before any command runs.
_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379"),
    decode_responses=True,
)


def publish_event(channel_id: int, event_type: str, data: dict) -> None:
    payload = json.dumps({"type": event_type, "data": data})
    redis_breaker.call(_client.publish, f"channel:{channel_id}", payload)


def subscribe_to_channel(channel_id: int):
    """Return a PubSub handle subscribed to this channel's Redis topic."""
    pubsub = redis_breaker.call(_client.pubsub, ignore_subscribe_messages=True)
    pubsub.subscribe(f"channel:{channel_id}")
    return pubsub


def publish_user_notification(user_id: int, notification: dict) -> None:
    redis_breaker.call(_client.publish, f"user:{user_id}", json.dumps(notification))
