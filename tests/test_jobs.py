import pytest
import jobs.tasks as tasks_module
from jobs.tasks import (
    send_notification,
    process_event,
    cleanup_old_notifications,
    send_notification_job,
)
from jobs.job_queue import enqueue_job, get_job_status, _CELERY_TO_JOB_STATE
from models import Notification, Event


def test_job_queuing(celery_eager, task_db, app_user, app_message):
    job_id = enqueue_job("send_notification", app_user.id, app_message.id)

    assert isinstance(job_id, str) and len(job_id) > 0

    n = task_db.query(Notification).filter(
        Notification.user_id == app_user.id,
        Notification.message_id == app_message.id,
    ).first()
    assert n is not None


def test_job_execution(task_db, app_user, app_message):
    result = send_notification(task_db, app_user.id, app_message.id)

    assert result["status"] == "success"
    assert "notification_id" in result

    n = task_db.query(Notification).filter(
        Notification.user_id == app_user.id,
        Notification.message_id == app_message.id,
    ).first()
    assert n is not None
    assert n.is_read is False


def test_job_execution_idempotent(task_db, app_user, app_message):
    send_notification(task_db, app_user.id, app_message.id)
    result = send_notification(task_db, app_user.id, app_message.id)

    assert result["status"] == "skipped"
    count = task_db.query(Notification).filter(
        Notification.user_id == app_user.id,
        Notification.message_id == app_message.id,
    ).count()
    assert count == 1


def test_failed_job_retry(celery_eager, monkeypatch):
    call_count = 0

    class FailingSession:
        def query(self, *a):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("simulated DB failure")
        def rollback(self): pass
        def close(self): pass

    monkeypatch.setattr(tasks_module, "_session_factory", FailingSession)

    result = send_notification_job.delay(1, 999)

    assert result.state == "FAILURE"
    assert call_count == 4  # 1 initial + 3 retries


def test_job_status_tracking():
    assert _CELERY_TO_JOB_STATE["SUCCESS"] == "success"
    assert _CELERY_TO_JOB_STATE["FAILURE"] == "failed"
    assert _CELERY_TO_JOB_STATE["STARTED"] == "processing"
    assert _CELERY_TO_JOB_STATE["RETRY"] == "retry"
    assert _CELERY_TO_JOB_STATE["PENDING"] == "pending"
    assert _CELERY_TO_JOB_STATE["REVOKED"] == "failed"


def test_get_job_status_success(celery_eager, task_db, app_user, app_message):
    from jobs.tasks import send_notification_job

    result = send_notification_job.delay(app_user.id, app_message.id)
    assert result.state == "SUCCESS"

    status = get_job_status(result.id)
    assert status["job_id"] == result.id
    assert "state" in status
    assert status["state"] in set(_CELERY_TO_JOB_STATE.values())


def test_concurrent_jobs(task_db, app_user, app_other_user, app_channel, app_message):
    from services.channels import join_channel
    join_channel(task_db, app_other_user.id, app_channel.id)

    r1 = send_notification(task_db, app_user.id, app_message.id)
    r2 = send_notification(task_db, app_other_user.id, app_message.id)

    assert r1["status"] == "success"
    assert r2["status"] == "success"

    total = task_db.query(Notification).filter(
        Notification.message_id == app_message.id
    ).count()
    assert total == 2


def test_process_event_job(task_db, app_user):
    result = process_event(task_db, app_user.id, "user.login", {"ip": "127.0.0.1"})

    assert result["status"] == "success"
    e = task_db.query(Event).filter(Event.id == result["event_id"]).first()
    assert e is not None
    assert e.action == "user.login"
    assert e.data["ip"] == "127.0.0.1"


def test_cleanup_old_notifications(task_db, app_user, app_message):
    from datetime import datetime, timedelta, timezone
    from models import Notification

    old = Notification(
        user_id=app_user.id,
        message_id=app_message.id,
        is_read=True,
        created_at=datetime.now(timezone.utc) - timedelta(days=60),
    )
    task_db.add(old)
    task_db.commit()

    result = cleanup_old_notifications(task_db, days=30)

    assert result["status"] == "success"
    assert result["deleted"] >= 1
    remaining = task_db.query(Notification).filter(
        Notification.user_id == app_user.id,
        Notification.message_id == app_message.id,
    ).first()
    assert remaining is None
