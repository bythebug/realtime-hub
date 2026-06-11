from sqlalchemy.orm import Session
from models import Channel, UserChannel


def create_channel(db: Session, creator_id: int, name: str) -> Channel:
    channel = Channel(name=name, creator_id=creator_id)
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def get_channel(db: Session, channel_id: int) -> Channel | None:
    return db.get(Channel, channel_id)


def list_user_channels(db: Session, user_id: int) -> list[Channel]:
    return (
        db.query(Channel)
        .join(UserChannel, UserChannel.channel_id == Channel.id)
        .filter(UserChannel.user_id == user_id)
        .all()
    )


def join_channel(db: Session, user_id: int, channel_id: int) -> UserChannel:
    if is_member(db, user_id, channel_id):
        raise ValueError(f"User {user_id} is already a member of channel {channel_id}")
    membership = UserChannel(user_id=user_id, channel_id=channel_id)
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership


def leave_channel(db: Session, user_id: int, channel_id: int) -> None:
    membership = (
        db.query(UserChannel)
        .filter(UserChannel.user_id == user_id, UserChannel.channel_id == channel_id)
        .first()
    )
    if not membership:
        raise ValueError(f"User {user_id} is not a member of channel {channel_id}")
    db.delete(membership)
    db.commit()


def is_member(db: Session, user_id: int, channel_id: int) -> bool:
    return (
        db.query(UserChannel)
        .filter(UserChannel.user_id == user_id, UserChannel.channel_id == channel_id)
        .first()
    ) is not None
