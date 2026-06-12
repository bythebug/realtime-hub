from celery.result import AsyncResult
from jobs.celery_app import celery

_TASK_MAP = {
    "send_notification":     "tasks.send_notification_job",
    "process_event":         "tasks.process_event_job",
    "cleanup_notifications": "tasks.cleanup_old_notifications_job",
}

_CELERY_TO_JOB_STATE: dict[str, str] = {
    "PENDING":  "pending",
    "RECEIVED": "pending",
    "STARTED":  "processing",
    "SUCCESS":  "success",
    "FAILURE":  "failed",
    "RETRY":    "retry",
    "REVOKED":  "failed",
}


def enqueue_job(task_name: str, *args, **kwargs) -> str:
    """Enqueue a named job and return its job ID.

    Uses .delay() so that task_always_eager=True in tests executes the task
    synchronously within the same process.
    """
    from jobs.tasks import send_notification_job, process_event_job, cleanup_old_notifications_job
    _tasks = {
        "send_notification":     send_notification_job,
        "process_event":         process_event_job,
        "cleanup_notifications": cleanup_old_notifications_job,
    }
    result = _tasks[task_name].delay(*args, **kwargs)
    return result.id


def get_job_status(job_id: str) -> dict:
    """Return current state and result for a job ID."""
    result = AsyncResult(job_id, app=celery)
    state = _CELERY_TO_JOB_STATE.get(result.state, "pending")
    return {
        "job_id": job_id,
        "state": state,
        "result": (
            result.result
            if result.ready() and not isinstance(result.result, Exception)
            else None
        ),
    }
