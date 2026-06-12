from datetime import datetime, timezone
from sqlalchemy.orm import Session
from models import Message, UserChannel
from services.channels import is_member

MAX_LENGTH = 5000


def _validate(content: str) -> None:
    if not content or not content.strip():
        raise ValueError("content cannot be empty")
    if len(content) > MAX_LENGTH:
        raise ValueError(f"content exceeds {MAX_LENGTH} characters")


def post_message(db: Session, user_id: int, channel_id: int, content: str) -> Message:
    _validate(content)
    if not is_member(db, user_id, channel_id):
        raise PermissionError("user is not a member of this channel")
    msg = Message(channel_id=channel_id, user_id=user_id, content=content.strip())
    db.add(msg)
    db.commit()
    db.refresh(msg)
    _enqueue_member_notifications(db, sender_id=user_id, channel_id=channel_id, message_id=msg.id)
    return msg


def _enqueue_member_notifications(
    db: Session, sender_id: int, channel_id: int, message_id: int
) -> None:
    """Fire-and-forget: notification failures must never fail the post."""
    try:
        from jobs.job_queue import enqueue_job
        members = db.query(UserChannel).filter(UserChannel.channel_id == channel_id).all()
        for m in members:
            if m.user_id != sender_id:
                enqueue_job("send_notification", m.user_id, message_id)
    except Exception:
        pass


def get_messages(
    db: Session,
    channel_id: int,
    limit: int = 50,
    offset: int = 0,
    order: str = "asc",
) -> list[Message]:
    q = db.query(Message).filter(
        Message.channel_id == channel_id,
        Message.deleted_at.is_(None),
    )
    if order == "desc":
        q = q.order_by(Message.created_at.desc(), Message.id.desc())
    else:
        q = q.order_by(Message.created_at.asc(), Message.id.asc())
    return q.limit(limit).offset(offset).all()


def get_message(db: Session, message_id: int) -> Message | None:
    return db.query(Message).filter(
        Message.id == message_id,
        Message.deleted_at.is_(None),
    ).first()


def delete_message(db: Session, message_id: int, user_id: int) -> None:
    msg = get_message(db, message_id)
    if not msg:
        raise ValueError("message not found")
    if msg.user_id != user_id:
        raise PermissionError("only the author can delete this message")
    msg.deleted_at = datetime.now(timezone.utc)
    db.commit()
