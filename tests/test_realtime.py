import pytest
from api.auth import make_token
from services.channels import join_channel


def _sio(flask_app, user_id):
    return flask_app.socketio.test_client(
        flask_app, query_string=f"token={make_token(user_id)}"
    )


# ------------------------------------------------------------------ connection

def test_websocket_connection(flask_app, app_user):
    client = _sio(flask_app, app_user.id)
    assert client.is_connected()
    client.disconnect()


def test_connection_rejected_without_token(flask_app):
    client = flask_app.socketio.test_client(flask_app)
    assert not client.is_connected()


def test_connection_rejected_with_invalid_token(flask_app):
    client = flask_app.socketio.test_client(flask_app, query_string="token=bad.token.here")
    assert not client.is_connected()


def test_disconnect_cleanup(flask_app, app_user):
    client = _sio(flask_app, app_user.id)
    assert client.is_connected()
    client.disconnect()
    assert not client.is_connected()


# ------------------------------------------------------------------ join / leave

def test_user_join_notification(flask_app, app_user, app_channel):
    client = _sio(flask_app, app_user.id)
    client.emit("join", {"channel_id": app_channel.id})

    received = client.get_received()
    join_events = [e for e in received if e["name"] == "user_joined"]
    assert len(join_events) == 1
    assert join_events[0]["args"][0]["channel_id"] == app_channel.id
    client.disconnect()


def test_join_non_member_channel_emits_error(flask_app, app_db, app_user):
    from services.channels import create_channel
    other_ch = create_channel(app_db, app_user.id, "private")

    client = _sio(flask_app, app_user.id)
    client.emit("join", {"channel_id": other_ch.id})

    received = client.get_received()
    errors = [e for e in received if e["name"] == "error"]
    assert len(errors) == 1
    client.disconnect()


# ------------------------------------------------------------------ message broadcast

def test_message_broadcast(flask_app, app_user, app_channel):
    client = _sio(flask_app, app_user.id)
    client.emit("join", {"channel_id": app_channel.id})
    client.get_received()

    client.emit("message", {"channel_id": app_channel.id, "content": "hello"})

    received = client.get_received()
    new_msgs = [e for e in received if e["name"] == "new_message"]
    assert len(new_msgs) == 1
    assert new_msgs[0]["args"][0]["content"] == "hello"
    assert new_msgs[0]["args"][0]["channel_id"] == app_channel.id
    client.disconnect()


def test_message_broadcast_invalid_content(flask_app, app_user, app_channel):
    client = _sio(flask_app, app_user.id)
    client.emit("join", {"channel_id": app_channel.id})
    client.get_received()

    client.emit("message", {"channel_id": app_channel.id, "content": ""})

    received = client.get_received()
    errors = [e for e in received if e["name"] == "error"]
    assert len(errors) == 1
    client.disconnect()


# ------------------------------------------------------------------ multiple clients

def test_multiple_clients(flask_app, app_db, app_user, app_other_user, app_channel):
    join_channel(app_db, app_other_user.id, app_channel.id)

    c1 = _sio(flask_app, app_user.id)
    c2 = _sio(flask_app, app_other_user.id)

    c1.emit("join", {"channel_id": app_channel.id})
    c2.emit("join", {"channel_id": app_channel.id})
    c1.get_received()
    c2.get_received()

    c1.emit("message", {"channel_id": app_channel.id, "content": "broadcast test"})

    c1_msgs = [e for e in c1.get_received() if e["name"] == "new_message"]
    c2_msgs = [e for e in c2.get_received() if e["name"] == "new_message"]

    assert len(c1_msgs) == 1
    assert len(c2_msgs) == 1
    assert c2_msgs[0]["args"][0]["content"] == "broadcast test"

    c1.disconnect()
    c2.disconnect()
