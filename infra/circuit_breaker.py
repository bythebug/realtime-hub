import logging
import threading
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED    = "closed"     # normal — requests flow through
    OPEN      = "open"       # failing fast — no requests attempted
    HALF_OPEN = "half_open"  # testing recovery — one request allowed through


class CircuitOpenError(Exception):
    """Raised when a call is attempted while the circuit is open."""
    def __init__(self, name: str):
        super().__init__(f"Circuit '{name}' is open — failing fast")
        self.circuit_name = name


class CircuitBreaker:
    """Thread-safe circuit breaker.

    State machine:
        CLOSED  --[N failures]--> OPEN
        OPEN    --[timeout]-----> HALF_OPEN
        HALF_OPEN --[success]---> CLOSED
        HALF_OPEN --[failure]---> OPEN
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and self._last_failure_time is not None
                and time.monotonic() - self._last_failure_time >= self.recovery_timeout
            ):
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit '%s' → HALF_OPEN (attempting recovery)", self.name)
            return self._state

    def call(self, func, *args, **kwargs):
        """Run func(*args, **kwargs) through the circuit breaker.

        Raises CircuitOpenError immediately when the circuit is OPEN.
        Records success/failure and transitions state accordingly.
        """
        if self.state == CircuitState.OPEN:
            raise CircuitOpenError(self.name)
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except CircuitOpenError:
            raise
        except Exception as exc:
            self._on_failure(exc)
            raise

    # ------------------------------------------------------------------

    def _on_success(self) -> None:
        with self._lock:
            if self._failure_count > 0:
                logger.info("Circuit '%s' → CLOSED (service recovered)", self.name)
            self._failure_count = 0
            self._state = CircuitState.CLOSED

    def _on_failure(self, exc: Exception) -> None:
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        "Circuit '%s' → OPEN after %d failures (last: %s)",
                        self.name,
                        self._failure_count,
                        exc,
                    )
                self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED (useful in tests and ops tooling)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
        logger.info("Circuit '%s' manually reset to CLOSED", self.name)

    def as_dict(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout_s": self.recovery_timeout,
            }


# ---- Pre-configured instances shared across the application ----
redis_breaker = CircuitBreaker("redis",    failure_threshold=5, recovery_timeout=30.0)
db_breaker    = CircuitBreaker("database", failure_threshold=3, recovery_timeout=60.0)
