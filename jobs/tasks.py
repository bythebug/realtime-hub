import logging
from datetime import datetime, timedelta, timezone
from jobs.celery_app import celery
from database import SessionLocal
from models import Notification, Event

logger = logging.getLogger(__name__)

# Overridable in tests via monkeypatch
_session_factory = SessionLocal


# ---- Pure business logic (no Celery dependency, directly testable) ----------

def send_notification(db, user_id: int, message_id: int) -> dict:
    """Create a notification (idempotent: skips if one already exists)."""
    existing = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.message_id == message_id,
    ).first()
    if existing:
        try:
            from infra.monitoring import record_notification
            record_notification("skipped")
        except Exception:
            pass
        return {"status": "skipped", "reason": "already exists"}
    n = Notification(user_id=user_id, message_id=message_id)
    db.add(n)
    db.commit()
    db.refresh(n)
    try:
        from infra.monitoring import record_notification
        record_notification("success")
    except Exception:
        pass
    return {"status": "success", "notification_id": n.id}


def process_event(db, user_id: int, action: str, data: dict) -> dict:
    """Append an event to the audit log."""
    event = Event(user_id=user_id, action=action, data=data)
    db.add(event)
    db.commit()
    db.refresh(event)
    return {"status": "success", "event_id": event.id}


def cleanup_old_notifications(db, days: int = 30) -> dict:
    """Hard-delete read notifications older than `days` days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = (
        db.query(Notification)
        .filter(Notification.is_read == True, Notification.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"status": "success", "deleted": deleted}


# ---- Celery task wrappers (retry + logging live here) -----------------------

@celery.task(bind=True, max_retries=3, name="tasks.send_notification_job")
def send_notification_job(self, user_id: int, message_id: int) -> dict:
    db = _session_factory()
    try:
        return send_notification(db, user_id, message_id)
    except Exception as exc:
        db.rollback()
        logger.warning(
            "send_notification_job attempt %d/%d failed: %s",
            self.request.retries + 1,
            self.max_retries + 1,
            exc,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    finally:
        db.close()


@celery.task(bind=True, max_retries=3, name="tasks.process_event_job")
def process_event_job(self, user_id: int, action: str, data: dict) -> dict:
    db = _session_factory()
    try:
        return process_event(db, user_id, action, data)
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
    finally:
        db.close()


@celery.task(name="tasks.cleanup_old_notifications_job")
def cleanup_old_notifications_job(days: int = 30) -> dict:
    db = _session_factory()
    try:
        return cleanup_old_notifications(db, days=days)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
