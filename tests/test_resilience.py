import pytest
import time
from unittest.mock import patch, MagicMock
from infra import redis_client as rc
from infra.circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from infra.monitoring import check_database, check_redis, get_health_status
from api.error_handlers import retry_with_backoff


def test_redis_connection_failure(client, app_user, app_channel, auth_headers):
    with patch.object(rc._client, "publish", side_effect=ConnectionError("Redis down")):
        resp = client.post(
            f"/channels/{app_channel.id}/messages",
            json={"content": "hello despite redis failure"},
            headers=auth_headers,
        )
    assert resp.status_code == 201
    assert resp.get_json()["content"] == "hello despite redis failure"


def test_redis_health_check_reports_error(client, monkeypatch):
    monkeypatch.setattr(rc._client, "ping", MagicMock(side_effect=ConnectionError("Redis down")))

    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "degraded"
    assert data["services"]["redis"]["status"] == "error"


def test_database_connection_failure():
    db = MagicMock()
    db.execute.side_effect = Exception("connection refused")

    result = check_database(db)
    assert result["status"] == "error"
    assert "connection refused" in result["detail"]


def test_health_check_db_down(client, monkeypatch):
    db = MagicMock()
    db.execute.side_effect = Exception("DB down")
    status = get_health_status(db)
    assert status["status"] == "degraded"
    assert status["services"]["database"]["status"] == "error"


def test_graceful_degradation(client, app_user, app_channel, auth_headers, monkeypatch):
    monkeypatch.setattr(rc._client, "publish", MagicMock(side_effect=ConnectionError("Redis down")))

    resp = client.post(
        f"/channels/{app_channel.id}/messages",
        json={"content": "degraded but saved"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["id"] is not None
    assert data["content"] == "degraded but saved"


def test_graceful_degradation_multiple_redis_failures(client, app_user, app_channel, auth_headers, monkeypatch):
    monkeypatch.setattr(rc._client, "publish", MagicMock(side_effect=ConnectionError()))

    for i in range(3):
        resp = client.post(
            f"/channels/{app_channel.id}/messages",
            json={"content": f"message {i}"},
            headers=auth_headers,
        )
        assert resp.status_code == 201


def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker("test-service", failure_threshold=3, recovery_timeout=0.05)

    def failing():
        raise ConnectionError("service unavailable")

    for _ in range(3):
        with pytest.raises(ConnectionError):
            cb.call(failing)

    assert cb.state == CircuitState.OPEN
    assert cb.as_dict()["failure_count"] == 3

    call_count = 0

    def counted_failing():
        nonlocal call_count
        call_count += 1
        raise ConnectionError()

    with pytest.raises(CircuitOpenError):
        cb.call(counted_failing)

    assert call_count == 0


def test_circuit_breaker_half_open_recovery():
    cb = CircuitBreaker("test-recovery", failure_threshold=2, recovery_timeout=0.05)

    def failing():
        raise ConnectionError()

    def succeeding():
        return "ok"

    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(failing)
    assert cb.state == CircuitState.OPEN

    time.sleep(0.1)
    assert cb.state == CircuitState.HALF_OPEN

    result = cb.call(succeeding)
    assert result == "ok"
    assert cb.state == CircuitState.CLOSED


def test_circuit_breaker_resets_on_manual_reset():
    cb = CircuitBreaker("test-reset", failure_threshold=2, recovery_timeout=60.0)

    def failing():
        raise RuntimeError("error")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            cb.call(failing)

    assert cb.state == CircuitState.OPEN
    cb.reset()
    assert cb.state == CircuitState.CLOSED
    assert cb.as_dict()["failure_count"] == 0


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code in (200, 503)

    data = resp.get_json()
    assert data["status"] in ("ok", "degraded")
    assert "services" in data
    for key in ("database", "redis", "job_queue"):
        assert key in data["services"]
        assert data["services"][key]["status"] in ("ok", "error", "degraded")


def test_health_check_all_ok(client):
    resp = client.get("/health")
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["services"]["database"]["status"] == "ok"


def test_circuit_breakers_endpoint(client):
    resp = client.get("/health/circuit-breakers")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "redis" in data
    assert "database" in data
    assert data["redis"]["state"] == "closed"
    assert data["database"]["state"] == "closed"


def test_retry_with_backoff_succeeds_eventually():
    call_count = 0

    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise IOError("temporary failure")
        return "done"

    result = retry_with_backoff(flaky, max_retries=3, base_delay=0.01)
    assert result == "done"
    assert call_count == 3


def test_retry_with_backoff_raises_after_max():
    def always_fails():
        raise IOError("permanent failure")

    with pytest.raises(IOError, match="permanent failure"):
        retry_with_backoff(always_fails, max_retries=2, base_delay=0.01)
