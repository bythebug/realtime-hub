import logging
import threading
from sqlalchemy import text
import redis_client as rc

logger = logging.getLogger(__name__)


# ---- Individual service checks ----

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
        from celery_app import celery
        _ = celery.conf.broker_url
        return {"status": "ok", "broker": celery.conf.broker_url}
    except Exception as exc:
        return {"status": "error", "detail": str(exc)}


def check_circuit_breakers() -> dict:
    from circuit_breaker import redis_breaker, db_breaker
    return {
        "redis":    redis_breaker.as_dict(),
        "database": db_breaker.as_dict(),
    }


# ---- Aggregate health status ----

def get_health_status(db) -> dict:
    db_check    = check_database(db)
    redis_check = check_redis()
    queue_check = check_job_queue()

    # System is degraded (but still serving) unless every service is ok.
    # Database down is the only hard dependency — all others degrade gracefully.
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


# ---- Background health logger ----

_stop_event = threading.Event()
_health_thread: threading.Thread | None = None


def start_health_logging(app, interval: int = 60) -> None:
    """Log system health every `interval` seconds in a background daemon thread."""
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
