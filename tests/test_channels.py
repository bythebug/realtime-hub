import pytest
from channels import (
    create_channel,
    get_channel,
    join_channel,
    leave_channel,
    list_user_channels,
    is_member,
)


def test_create_channel(db, user):
    ch = create_channel(db, user.id, "announcements")
    assert ch.id is not None
    assert ch.name == "announcements"
    assert ch.creator_id == user.id


def test_get_channel(db, channel):
    fetched = get_channel(db, channel.id)
    assert fetched is not None
    assert fetched.id == channel.id
    assert fetched.name == channel.name


def test_get_channel_not_found(db):
    assert get_channel(db, 9999) is None


def test_join_channel(db, other_user, channel):
    membership = join_channel(db, other_user.id, channel.id)
    assert membership.user_id == other_user.id
    assert membership.channel_id == channel.id
    assert is_member(db, other_user.id, channel.id)


def test_leave_channel(db, user, channel):
    join_channel(db, user.id, channel.id)
    assert is_member(db, user.id, channel.id)

    leave_channel(db, user.id, channel.id)
    assert not is_member(db, user.id, channel.id)


def test_leave_channel_not_member_raises(db, user, channel):
    with pytest.raises(ValueError, match="not a member"):
        leave_channel(db, user.id, channel.id)


def test_list_channels(db, user):
    ch1 = create_channel(db, user.id, "general")
    ch2 = create_channel(db, user.id, "random")
    join_channel(db, user.id, ch1.id)
    join_channel(db, user.id, ch2.id)

    channels = list_user_channels(db, user.id)
    channel_names = {c.name for c in channels}
    assert "general" in channel_names
    assert "random" in channel_names


def test_list_channels_empty(db, user):
    assert list_user_channels(db, user.id) == []


def test_cannot_join_same_channel_twice(db, user, channel):
    join_channel(db, user.id, channel.id)
    with pytest.raises(ValueError, match="already a member"):
        join_channel(db, user.id, channel.id)


def test_is_member_false_for_non_member(db, other_user, channel):
    assert not is_member(db, other_user.id, channel.id)
