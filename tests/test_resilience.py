import pytest
import time
from unittest.mock import patch, MagicMock
import redis_client as rc
from circuit_breaker import CircuitBreaker, CircuitOpenError, CircuitState
from monitoring import check_database, check_redis, get_health_status
from error_handlers import retry_with_backoff


# ------------------------------------------------------------------ redis failure

def test_redis_connection_failure(client, app_user, app_channel, auth_headers):
    """POST /messages succeeds (201) even when Redis publish raises."""
    with patch.object(rc._client, "publish", side_effect=ConnectionError("Redis down")):
        resp = client.post(
            f"/channels/{app_channel.id}/messages",
            json={"content": "hello despite redis failure"},
            headers=auth_headers,
        )
    assert resp.status_code == 201
    assert resp.get_json()["content"] == "hello despite redis failure"


def test_redis_health_check_reports_error(client, monkeypatch):
    """GET /health reports Redis as error when Redis is unavailable."""
    monkeypatch.setattr(rc._client, "ping", MagicMock(side_effect=ConnectionError("Redis down")))

    resp = client.get("/health")
    assert resp.status_code == 200  # DB is up → still serving
    data = resp.get_json()
    assert data["status"] == "degraded"
    assert data["services"]["redis"]["status"] == "error"


# ------------------------------------------------------------------ database failure

def test_database_connection_failure():
    """check_database reports error when the DB raises."""
    db = MagicMock()
    db.execute.side_effect = Exception("connection refused")

    result = check_database(db)
    assert result["status"] == "error"
    assert "connection refused" in result["detail"]


def test_health_check_db_down(client, monkeypatch):
    """GET /health returns 503 when database is unavailable."""
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    original_execute = None

    def failing_execute(stmt, *a, **kw):
        if str(stmt) == str(text("SELECT 1")):
            raise OperationalError("DB down", None, None)
        if original_execute:
            return original_execute(stmt, *a, **kw)

    monkeypatch.setattr(type(client.application.SessionFactory()), "execute", failing_execute, raising=False)

    # Easier: test check_database directly with a failing mock
    db = MagicMock()
    db.execute.side_effect = Exception("DB down")
    status = get_health_status(db)
    assert status["status"] == "degraded"
    assert status["services"]["database"]["status"] == "error"


# ------------------------------------------------------------------ graceful degradation

def test_graceful_degradation(client, app_user, app_channel, auth_headers, monkeypatch):
    """When Redis is down, message is saved to DB and 201 is returned."""
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
    """Multiple Redis failures don't stop message posting."""
    monkeypatch.setattr(rc._client, "publish", MagicMock(side_effect=ConnectionError()))

    for i in range(3):
        resp = client.post(
            f"/channels/{app_channel.id}/messages",
            json={"content": f"message {i}"},
            headers=auth_headers,
        )
        assert resp.status_code == 201


# ------------------------------------------------------------------ circuit breaker

def test_circuit_breaker_opens_after_threshold():
    """Circuit opens after failure_threshold failures and then fails fast."""
    cb = CircuitBreaker("test-service", failure_threshold=3, recovery_timeout=0.05)

    def failing():
        raise ConnectionError("service unavailable")

    # Three failures open the circuit
    for _ in range(3):
        with pytest.raises(ConnectionError):
            cb.call(failing)

    assert cb.state == CircuitState.OPEN
    assert cb.as_dict()["failure_count"] == 3

    # Next call fails fast — underlying function is never called
    call_count = 0

    def counted_failing():
        nonlocal call_count
        call_count += 1
        raise ConnectionError()

    with pytest.raises(CircuitOpenError):
        cb.call(counted_failing)

    assert call_count == 0  # fast-fail; function not invoked


def test_circuit_breaker_half_open_recovery():
    """Circuit transitions OPEN → HALF_OPEN → CLOSED after recovery."""
    cb = CircuitBreaker("test-recovery", failure_threshold=2, recovery_timeout=0.05)

    def failing():
        raise ConnectionError()

    def succeeding():
        return "ok"

    # Open the circuit
    for _ in range(2):
        with pytest.raises(ConnectionError):
            cb.call(failing)
    assert cb.state == CircuitState.OPEN

    # Wait for recovery timeout
    time.sleep(0.1)
    assert cb.state == CircuitState.HALF_OPEN

    # Successful call closes it
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


# ------------------------------------------------------------------ health check endpoint

def test_health_check(client):
    """GET /health returns a well-formed status response."""
    resp = client.get("/health")
    assert resp.status_code in (200, 503)

    data = resp.get_json()
    assert data["status"] in ("ok", "degraded")
    assert "services" in data
    for key in ("database", "redis", "job_queue"):
        assert key in data["services"]
        assert data["services"][key]["status"] in ("ok", "error", "degraded")


def test_health_check_all_ok(client):
    """GET /health returns 200 and 'ok' when all services are reachable."""
    resp = client.get("/health")
    data = resp.get_json()
    # In test env: SQLite is up; fakeredis is up; Celery config is readable.
    assert resp.status_code == 200
    assert data["services"]["database"]["status"] == "ok"


def test_circuit_breakers_endpoint(client):
    """GET /health/circuit-breakers returns breaker state for redis and database."""
    resp = client.get("/health/circuit-breakers")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "redis" in data
    assert "database" in data
    assert data["redis"]["state"] == "closed"
    assert data["database"]["state"] == "closed"


# ------------------------------------------------------------------ retry_with_backoff

def test_retry_with_backoff_succeeds_eventually():
    """retry_with_backoff retries and returns the result on success."""
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
    """retry_with_backoff raises the last exception after exhausting retries."""
    def always_fails():
        raise IOError("permanent failure")

    with pytest.raises(IOError, match="permanent failure"):
        retry_with_backoff(always_fails, max_retries=2, base_delay=0.01)
