from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, JSON, UniqueConstraint, Index
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), nullable=False, unique=True)
    email = Column(String(255), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    channels = relationship("UserChannel", back_populates="user")
    messages = relationship("Message", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    events = relationship("Event", back_populates="user")
    created_channels = relationship("Channel", back_populates="creator")


class Channel(Base):
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    creator_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    creator = relationship("User", back_populates="created_channels")
    members = relationship("UserChannel", back_populates="channel")
    messages = relationship("Message", back_populates="channel")

    __table_args__ = (
        Index("ix_channels_creator_id", "creator_id"),
    )


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    channel = relationship("Channel", back_populates="messages")
    user = relationship("User", back_populates="messages")
    notifications = relationship("Notification", back_populates="message")

    __table_args__ = (
        Index("ix_messages_channel_id", "channel_id"),
        Index("ix_messages_user_id", "user_id"),
        # composite index for fetching channel messages in order
        Index("ix_messages_channel_created", "channel_id", "created_at"),
    )


class UserChannel(Base):
    """Join table for the many-to-many relationship between User and Channel."""
    __tablename__ = "user_channels"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="channels")
    channel = relationship("Channel", back_populates="members")

    __table_args__ = (
        UniqueConstraint("user_id", "channel_id", name="uq_user_channel"),
        Index("ix_user_channels_user_id", "user_id"),
        Index("ix_user_channels_channel_id", "channel_id"),
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="notifications")
    message = relationship("Message", back_populates="notifications")

    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_notification_user_message"),
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_message_id", "message_id"),
        # partial-style: most queries filter on unread notifications
        Index("ix_notifications_user_unread", "user_id", "is_read"),
    )


class Event(Base):
    """Append-only audit log. Never update or delete rows."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(100), nullable=False)
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)

    user = relationship("User", back_populates="events")

    __table_args__ = (
        Index("ix_events_user_id", "user_id"),
        Index("ix_events_action", "action"),
        Index("ix_events_created_at", "created_at"),
    )
