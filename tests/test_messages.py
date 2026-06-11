import pytest
from channels import join_channel


# ------------------------------------------------------------------ post message

def test_post_message(client, app_channel, auth_headers):
    resp = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "hello world"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["content"] == "hello world"
    assert data["channel_id"] == app_channel.id


def test_post_message_requires_auth(client, app_channel):
    resp = client.post(f"/channels/{app_channel.id}/messages", json={"content": "hi"})
    assert resp.status_code == 401


def test_post_message_non_member_forbidden(client, app_channel, other_auth_headers):
    resp = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "hi"},
        headers=other_auth_headers,
    )
    assert resp.status_code == 403


# ------------------------------------------------------------------ get messages

def test_get_messages(client, app_channel, auth_headers):
    client.post(f"/channels/{app_channel.id}/messages", json={"content": "msg 1"}, headers=auth_headers)
    client.post(f"/channels/{app_channel.id}/messages", json={"content": "msg 2"}, headers=auth_headers)

    resp = client.get(f"/channels/{app_channel.id}/messages", headers=auth_headers)
    assert resp.status_code == 200
    msgs = resp.get_json()
    assert len(msgs) == 2
    assert msgs[0]["content"] == "msg 1"
    assert msgs[1]["content"] == "msg 2"


def test_get_messages_non_member_forbidden(client, app_channel, other_auth_headers):
    resp = client.get(f"/channels/{app_channel.id}/messages", headers=other_auth_headers)
    assert resp.status_code == 403


# ------------------------------------------------------------------ pagination

def test_pagination(client, app_channel, auth_headers):
    for i in range(1, 4):
        client.post(f"/channels/{app_channel.id}/messages", json={"content": f"msg {i}"}, headers=auth_headers)

    page1 = client.get(
        f"/channels/{app_channel.id}/messages?limit=2&offset=0",
        headers=auth_headers,
    ).get_json()
    assert len(page1) == 2
    assert page1[0]["content"] == "msg 1"
    assert page1[1]["content"] == "msg 2"

    page2 = client.get(
        f"/channels/{app_channel.id}/messages?limit=2&offset=2",
        headers=auth_headers,
    ).get_json()
    assert len(page2) == 1
    assert page2[0]["content"] == "msg 3"


def test_newest_first_order(client, app_channel, auth_headers):
    for i in range(1, 4):
        client.post(f"/channels/{app_channel.id}/messages", json={"content": f"msg {i}"}, headers=auth_headers)

    msgs = client.get(
        f"/channels/{app_channel.id}/messages?order=desc",
        headers=auth_headers,
    ).get_json()
    assert msgs[0]["content"] == "msg 3"
    assert msgs[-1]["content"] == "msg 1"


# ------------------------------------------------------------------ single message

def test_get_single_message(client, app_channel, auth_headers):
    posted = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "single"},
        headers=auth_headers,
    ).get_json()

    resp = client.get(f"/messages/{posted['id']}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["content"] == "single"


def test_get_message_not_found(client, auth_headers):
    resp = client.get("/messages/9999", headers=auth_headers)
    assert resp.status_code == 404


# ------------------------------------------------------------------ delete message

def test_delete_message(client, app_channel, auth_headers):
    posted = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "to be deleted"},
        headers=auth_headers,
    ).get_json()

    resp = client.delete(f"/messages/{posted['id']}", headers=auth_headers)
    assert resp.status_code == 204

    # soft-deleted: no longer visible
    fetch = client.get(f"/messages/{posted['id']}", headers=auth_headers)
    assert fetch.status_code == 404


def test_unauthorized_delete(client, app_db, app_channel, app_other_user, auth_headers, other_auth_headers):
    # other_user joins the channel so they can attempt the delete
    join_channel(app_db, app_other_user.id, app_channel.id)

    posted = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "alice's message"},
        headers=auth_headers,
    ).get_json()

    resp = client.delete(f"/messages/{posted['id']}", headers=other_auth_headers)
    assert resp.status_code == 403


# ------------------------------------------------------------------ content validation

def test_invalid_content_empty(client, app_channel, auth_headers):
    resp = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": ""},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_invalid_content_whitespace_only(client, app_channel, auth_headers):
    resp = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "   "},
        headers=auth_headers,
    )
    assert resp.status_code == 422


def test_invalid_content_too_long(client, app_channel, auth_headers):
    resp = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "x" * 5001},
        headers=auth_headers,
    )
    assert resp.status_code == 422
