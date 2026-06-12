import logging
import time
from flask import jsonify

logger = logging.getLogger(__name__)


def register_error_handlers(app) -> None:
    """Attach JSON error handlers to a Flask app."""

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "bad request", "detail": str(e.description)}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"error": "unauthorized"}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"error": "forbidden"}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(422)
    def unprocessable(e):
        return jsonify({"error": "unprocessable entity", "detail": str(e.description)}), 422

    @app.errorhandler(500)
    def internal_error(e):
        logger.error("Unhandled exception: %s", e, exc_info=True)
        return jsonify({"error": "internal server error"}), 500


def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 0.5,
    exceptions: tuple = (Exception,),
):
    """Call func(), retrying with exponential backoff on failure.

    Args:
        func:         Zero-argument callable to attempt.
        max_retries:  Maximum number of retry attempts (not counting the first).
        base_delay:   Initial delay in seconds; doubles on each retry.
        exceptions:   Exception types that trigger a retry.

    Returns:
        The return value of func() on success.

    Raises:
        The last exception raised by func() after all retries are exhausted.
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return func()
        except exceptions as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "retry_with_backoff: attempt %d/%d failed (%s), retrying in %.2fs",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                    delay,
                )
                time.sleep(delay)
    raise last_exc
