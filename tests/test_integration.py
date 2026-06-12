"""
Integration tests: exercise multiple layers together (HTTP + WebSocket + DB + jobs).
"""
import pytest
from auth import make_token
from channels import join_channel
from models import Notification


# ------------------------------------------------------------------ full message flow

def test_full_message_flow(
    celery_eager, flask_app, app_db, app_user, app_other_user,
    app_channel, auth_headers, task_db, monkeypatch,
):
    """Post message via HTTP → broadcast via Socket.IO → notification via job."""
    import tasks as t
    monkeypatch.setattr(t, "_session_factory", lambda: task_db)

    join_channel(app_db, app_other_user.id, app_channel.id)

    # other_user connects via Socket.IO and joins the channel room
    other_sio = flask_app.socketio.test_client(
        flask_app, query_string=f"token={make_token(app_other_user.id)}"
    )
    other_sio.emit("join", {"channel_id": app_channel.id})
    other_sio.get_received()  # clear join events

    # Post a message via HTTP as app_user
    http = flask_app.test_client()
    resp = http.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "integration test message"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    msg_data = resp.get_json()
    assert msg_data["content"] == "integration test message"
    assert msg_data["id"] is not None

    # other_user receives the Socket.IO broadcast
    received = other_sio.get_received()
    new_msgs = [e for e in received if e["name"] == "new_message"]
    assert len(new_msgs) == 1
    assert new_msgs[0]["args"][0]["content"] == "integration test message"
    assert new_msgs[0]["args"][0]["channel_id"] == app_channel.id

    # Background job created a Notification for other_user
    n = task_db.query(Notification).filter(
        Notification.user_id == app_other_user.id,
        Notification.message_id == msg_data["id"],
    ).first()
    assert n is not None
    assert n.is_read is False

    other_sio.disconnect()


def test_full_message_flow_via_socket(
    flask_app, app_db, app_user, app_other_user, app_channel,
):
    """Send message via Socket.IO → both sender and joined user receive broadcast."""
    join_channel(app_db, app_other_user.id, app_channel.id)

    c1 = flask_app.socketio.test_client(
        flask_app, query_string=f"token={make_token(app_user.id)}"
    )
    c2 = flask_app.socketio.test_client(
        flask_app, query_string=f"token={make_token(app_other_user.id)}"
    )

    c1.emit("join", {"channel_id": app_channel.id})
    c2.emit("join", {"channel_id": app_channel.id})
    c1.get_received()
    c2.get_received()

    c1.emit("message", {"channel_id": app_channel.id, "content": "socket message"})

    c1_msgs = [e for e in c1.get_received() if e["name"] == "new_message"]
    c2_msgs = [e for e in c2.get_received() if e["name"] == "new_message"]
    assert len(c1_msgs) == 1
    assert len(c2_msgs) == 1
    assert c2_msgs[0]["args"][0]["content"] == "socket message"

    c1.disconnect()
    c2.disconnect()


# ------------------------------------------------------------------ concurrent messages

def test_concurrent_messages(client, app_user, app_channel, auth_headers):
    """Multiple messages all stored correctly with unique IDs."""
    contents = [f"message {i}" for i in range(5)]

    ids = []
    for content in contents:
        resp = client.post(
            f"/channels/{app_channel.id}/messages",
            json={"content": content},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        ids.append(resp.get_json()["id"])

    assert len(set(ids)) == 5  # all unique

    resp = client.get(
        f"/channels/{app_channel.id}/messages?limit=10",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    stored = resp.get_json()
    assert len(stored) == 5
    assert all(m["user_id"] == app_user.id for m in stored)


def test_concurrent_messages_multiple_users(
    client, flask_app, app_db, app_user, app_other_user, app_channel,
    auth_headers, other_auth_headers,
):
    """Messages from different users are stored and attributed correctly."""
    join_channel(app_db, app_other_user.id, app_channel.id)

    client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "from alice"},
        headers=auth_headers,
    )
    http2 = flask_app.test_client()
    http2.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "from bob"},
        headers=other_auth_headers,
    )

    resp = client.get(
        f"/channels/{app_channel.id}/messages",
        headers=auth_headers,
    )
    msgs = resp.get_json()
    assert len(msgs) == 2
    authors = {m["content"]: m["user_id"] for m in msgs}
    assert authors["from alice"] == app_user.id
    assert authors["from bob"] == app_other_user.id


# ------------------------------------------------------------------ channel join / leave

def test_channel_join_leave(flask_app, app_db, app_user, app_other_user, app_channel):
    """Client stops receiving messages after leaving the Socket.IO room."""
    join_channel(app_db, app_other_user.id, app_channel.id)

    alice = flask_app.socketio.test_client(
        flask_app, query_string=f"token={make_token(app_user.id)}"
    )
    bob = flask_app.socketio.test_client(
        flask_app, query_string=f"token={make_token(app_other_user.id)}"
    )

    alice.emit("join", {"channel_id": app_channel.id})
    bob.emit("join", {"channel_id": app_channel.id})
    alice.get_received()
    bob.get_received()

    # Before bob leaves: alice's message reaches him
    alice.emit("message", {"channel_id": app_channel.id, "content": "before leave"})
    bob_before = [e for e in bob.get_received() if e["name"] == "new_message"]
    assert len(bob_before) == 1

    # Bob leaves the room
    bob.emit("leave", {"channel_id": app_channel.id})
    alice.get_received()
    bob.get_received()

    # After bob leaves: alice's message does NOT reach him
    alice.emit("message", {"channel_id": app_channel.id, "content": "after leave"})
    bob_after = [e for e in bob.get_received() if e["name"] == "new_message"]
    assert len(bob_after) == 0

    # Alice still receives her own message
    alice_after = [e for e in alice.get_received() if e["name"] == "new_message"]
    assert len(alice_after) == 1

    alice.disconnect()
    bob.disconnect()


# ------------------------------------------------------------------ message ordering

def test_message_ordering(client, app_user, app_channel, auth_headers):
    """Messages are returned oldest-first by default, newest-first with order=desc."""
    contents = ["alpha", "beta", "gamma", "delta", "epsilon"]
    for content in contents:
        resp = client.post(
            f"/channels/{app_channel.id}/messages",
            json={"content": content},
            headers=auth_headers,
        )
        assert resp.status_code == 201

    # Ascending (default)
    resp_asc = client.get(
        f"/channels/{app_channel.id}/messages",
        headers=auth_headers,
    )
    asc = [m["content"] for m in resp_asc.get_json()]
    assert asc == contents

    # Descending
    resp_desc = client.get(
        f"/channels/{app_channel.id}/messages?order=desc",
        headers=auth_headers,
    )
    desc = [m["content"] for m in resp_desc.get_json()]
    assert desc == list(reversed(contents))


def test_message_pagination_ordering(client, app_user, app_channel, auth_headers):
    """Pagination preserves ordering — pages are contiguous and non-overlapping."""
    for i in range(6):
        client.post(
            f"/channels/{app_channel.id}/messages",
            json={"content": str(i)},
            headers=auth_headers,
        )

    p1 = client.get(
        f"/channels/{app_channel.id}/messages?limit=3&offset=0",
        headers=auth_headers,
    ).get_json()
    p2 = client.get(
        f"/channels/{app_channel.id}/messages?limit=3&offset=3",
        headers=auth_headers,
    ).get_json()

    all_contents = [m["content"] for m in p1 + p2]
    assert all_contents == [str(i) for i in range(6)]


# ------------------------------------------------------------------ metrics endpoint

def test_metrics_endpoint(client):
    """GET /metrics returns Prometheus-format text."""
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"realtime_hub" in resp.data or b"prometheus" in resp.data.lower()


def test_metrics_increment_on_post(client, app_user, app_channel, auth_headers):
    """Posting a message increments the messages_posted counter."""
    resp = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "metrics test"},
        headers=auth_headers,
    )
    assert resp.status_code == 201

    metrics_resp = client.get("/metrics")
    assert metrics_resp.status_code == 200


# ------------------------------------------------------------------ register endpoint

def test_register_endpoint(client):
    """POST /auth/register creates a user and returns a JWT token."""
    resp = client.post(
        "/auth/register",
        json={
            "username": "newuser_integration",
            "email": "newuser_integration@test.com",
            "password": "testpassword",
        },
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert "token" in data
    assert "user_id" in data
    assert isinstance(data["token"], str)


def test_create_channel_endpoint(client, app_user, auth_headers):
    """POST /channels creates a channel and auto-joins the creator."""
    resp = client.post(
        "/channels",
        json={"name": "new-integration-channel"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["name"] == "new-integration-channel"
    assert "id" in data
