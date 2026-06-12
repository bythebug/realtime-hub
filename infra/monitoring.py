import json
import logging
import threading
from sqlalchemy import text
from infra import redis_client as rc

logger = logging.getLogger(__name__)


# ---- Prometheus metrics -------------------------------------------------------
try:
    from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

    messages_posted = Counter(
        "realtime_hub_messages_total",
        "Total messages posted",
        ["channel_id"],
    )
    message_post_latency = Histogram(
        "realtime_hub_message_post_duration_seconds",
        "End-to-end time to post a message (DB save + broadcast)",
        buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    )
    notifications_created = Counter(
        "realtime_hub_notifications_total",
        "Total notifications processed",
        ["status"],
    )
    redis_publishes = Counter(
        "realtime_hub_redis_publishes_total",
        "Total Redis publish attempts",
        ["status"],
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    generate_latest = None
    CONTENT_TYPE_LATEST = "text/plain"


# ---- Metric helpers ----------------------------------------------------------

def record_message_posted(channel_id: int, duration_seconds: float) -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        messages_posted.labels(channel_id=str(channel_id)).inc()
        message_post_latency.observe(duration_seconds)
    except Exception:
        pass


def record_notification(status: str) -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        notifications_created.labels(status=status).inc()
    except Exception:
        pass


def record_redis_publish(success: bool) -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    try:
        redis_publishes.labels(status="success" if success else "failure").inc()
    except Exception:
        pass


def get_prometheus_metrics() -> tuple[bytes, str]:
    if not _PROMETHEUS_AVAILABLE or generate_latest is None:
        return b"# prometheus_client not installed\n", "text/plain"
    return generate_latest(), CONTENT_TYPE_LATEST


# ---- Structured JSON logging -------------------------------------------------

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts":     self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level":  record.levelname,
            "logger": record.name,
            "msg":    record.getMessage(),
            "module": record.module,
            "fn":     record.funcName,
            "line":   record.lineno,
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(handler)


# ---- Service checks ----------------------------------------------------------

def check_database(db) -> dict:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def check_redis() -> dict:
    try:
        rc._client.ping()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def check_job_queue() -> dict:
    try:
        from jobs.celery_app import celery
        _ = celery.conf.broker_url
        return {"status": "ok", "broker": celery.conf.broker_url}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def check_circuit_breakers() -> dict:
    from infra.circuit_breaker import redis_breaker, db_breaker
    return {
        "redis":    redis_breaker.as_dict(),
        "database": db_breaker.as_dict(),
    }


# ---- Aggregate health --------------------------------------------------------

def get_health_status(db) -> dict:
    db_check    = check_database(db)
    redis_check = check_redis()
    queue_check = check_job_queue()

    overall = "ok" if all(
        s["status"] == "ok" for s in [db_check, redis_check, queue_check]
    ) else "degraded"

    return {
        "status": overall,
        "services": {
            "database":  db_check,
            "redis":     redis_check,
            "job_queue": queue_check,
        },
    }


# ---- Background health logger ------------------------------------------------

_stop_event = threading.Event()
_health_thread: threading.Thread | None = None


def start_health_logging(app, interval: int = 60) -> None:
    global _health_thread
    _stop_event.clear()

    def _loop() -> None:
        while not _stop_event.wait(timeout=interval):
            with app.app_context():
                from database import SessionLocal
                db = SessionLocal()
                try:
                    status = get_health_status(db)
                    level = logging.WARNING if status["status"] != "ok" else logging.INFO
                    logger.log(level, "Health: %s", status)
                except Exception as exc:
                    logger.error("Health logger error: %s", exc)
                finally:
                    db.close()

    _health_thread = threading.Thread(target=_loop, daemon=True, name="health-logger")
    _health_thread.start()
    logger.info("Health logger started (interval=%ds)", interval)


def stop_health_logging() -> None:
    _stop_event.set()
