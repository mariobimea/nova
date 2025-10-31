"""
Circuit Breaker Pattern for E2B Sandbox

Prevents cascading failures when E2B is down by temporarily blocking requests
after too many consecutive failures.

States:
- CLOSED: Normal operation, requests go through
- OPEN: Too many failures, blocking requests (fast-fail)
- HALF_OPEN: Testing if service recovered (allows 1 request)

Example:
    breaker = CircuitBreaker(failure_threshold=5, timeout=300)

    if breaker.is_open():
        raise E2BConnectionError("E2B circuit breaker is OPEN")

    try:
        result = execute_code_in_e2b(code)
        breaker.record_success()
    except Exception as e:
        breaker.record_failure()
        raise
"""

import time
import threading
import logging
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class CircuitBreakerState:
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker implementation for E2B sandbox calls.

    Prevents overloading E2B when it's experiencing issues.
    """

    def __init__(
        self,
        failure_threshold: int = 5,  # Open after 5 consecutive failures
        timeout: int = 300,  # Retry after 5 minutes
        half_open_max_calls: int = 1  # Allow 1 test call in HALF_OPEN state
    ):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening
            timeout: Seconds to wait before attempting recovery (HALF_OPEN)
            half_open_max_calls: Number of test calls allowed in HALF_OPEN state
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitBreakerState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[datetime] = None
        self._half_open_calls = 0

        # Thread lock for state changes
        self._lock = threading.Lock()

        logger.info(f"CircuitBreaker initialized: threshold={failure_threshold}, timeout={timeout}s")

    @property
    def state(self) -> str:
        """Get current circuit breaker state"""
        with self._lock:
            return self._state

    def is_open(self) -> bool:
        """Check if circuit is open (blocking requests)"""
        with self._lock:
            # If OPEN and timeout passed, transition to HALF_OPEN
            if self._state == CircuitBreakerState.OPEN:
                if self._last_failure_time:
                    elapsed = (datetime.utcnow() - self._last_failure_time).total_seconds()
                    if elapsed >= self.timeout:
                        logger.info("CircuitBreaker: Transitioning OPEN → HALF_OPEN (timeout passed)")
                        self._state = CircuitBreakerState.HALF_OPEN
                        self._half_open_calls = 0
                        return False

                return True

            # If HALF_OPEN and max test calls reached, stay closed
            if self._state == CircuitBreakerState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    logger.warning("CircuitBreaker: HALF_OPEN max calls reached, blocking request")
                    return True

            return False

    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)"""
        return self.state == CircuitBreakerState.CLOSED

    def is_half_open(self) -> bool:
        """Check if circuit is half-open (testing recovery)"""
        return self.state == CircuitBreakerState.HALF_OPEN

    def record_success(self):
        """Record successful call (reset failure counter)"""
        with self._lock:
            previous_state = self._state

            # Reset failure count
            self._failure_count = 0
            self._last_failure_time = None

            # Transition to CLOSED if we were HALF_OPEN
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.CLOSED
                self._half_open_calls = 0
                logger.info("CircuitBreaker: Transitioning HALF_OPEN → CLOSED (success)")
            elif self._state == CircuitBreakerState.OPEN:
                # Shouldn't happen, but handle it
                self._state = CircuitBreakerState.CLOSED
                logger.warning("CircuitBreaker: Transitioning OPEN → CLOSED (success)")

            if previous_state != CircuitBreakerState.CLOSED:
                logger.info(f"CircuitBreaker: State={self._state}, Failures=0")

    def record_failure(self):
        """Record failed call (increment failure counter)"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.utcnow()

            previous_state = self._state

            # If HALF_OPEN, one failure immediately opens the circuit
            if self._state == CircuitBreakerState.HALF_OPEN:
                self._state = CircuitBreakerState.OPEN
                logger.warning(
                    f"CircuitBreaker: Transitioning HALF_OPEN → OPEN "
                    f"(test call failed, will retry in {self.timeout}s)"
                )

            # If CLOSED and threshold reached, open the circuit
            elif self._state == CircuitBreakerState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    self._state = CircuitBreakerState.OPEN
                    logger.error(
                        f"CircuitBreaker: Transitioning CLOSED → OPEN "
                        f"({self._failure_count} consecutive failures, "
                        f"will retry in {self.timeout}s)"
                    )

            if self._state == CircuitBreakerState.HALF_OPEN:
                self._half_open_calls += 1

            logger.warning(
                f"CircuitBreaker: State={self._state}, "
                f"Failures={self._failure_count}/{self.failure_threshold}"
            )

    def reset(self):
        """Manually reset circuit breaker to CLOSED state"""
        with self._lock:
            previous_state = self._state
            self._state = CircuitBreakerState.CLOSED
            self._failure_count = 0
            self._last_failure_time = None
            self._half_open_calls = 0

            if previous_state != CircuitBreakerState.CLOSED:
                logger.info(f"CircuitBreaker: Manually reset {previous_state} → CLOSED")

    def get_status(self) -> dict:
        """Get circuit breaker status (for monitoring)"""
        with self._lock:
            return {
                "state": self._state,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "last_failure": self._last_failure_time.isoformat() if self._last_failure_time else None,
                "timeout_seconds": self.timeout,
                "half_open_calls": self._half_open_calls if self._state == CircuitBreakerState.HALF_OPEN else None,
            }


# ============================================================================
# GLOBAL CIRCUIT BREAKER INSTANCE
# ============================================================================

# Shared circuit breaker for all E2B calls
# - Opens after 5 consecutive failures
# - Blocks requests for 5 minutes
# - Then allows 1 test call to check recovery
e2b_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    timeout=300,  # 5 minutes
    half_open_max_calls=1
)
