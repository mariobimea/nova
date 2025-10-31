"""
Unit Tests for Circuit Breaker

Tests cover:
- State transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Failure threshold behavior
- Timeout and recovery
- Thread safety
- Success/failure recording
"""

import pytest
import time
from datetime import datetime, timedelta

from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerState


# ============================================================================
# BASIC FUNCTIONALITY TESTS
# ============================================================================

@pytest.mark.unit
def test_circuit_breaker_initial_state():
    """Test circuit breaker starts in CLOSED state"""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60)

    assert breaker.state == CircuitBreakerState.CLOSED
    assert breaker.is_closed()
    assert not breaker.is_open()
    assert not breaker.is_half_open()


@pytest.mark.unit
def test_circuit_breaker_single_failure():
    """Test single failure doesn't open circuit"""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60)

    breaker.record_failure()

    assert breaker.is_closed()
    assert not breaker.is_open()


@pytest.mark.unit
def test_circuit_breaker_opens_after_threshold():
    """Test circuit opens after reaching failure threshold"""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60)

    # Record 3 consecutive failures
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_failure()

    # Circuit should be OPEN
    assert breaker.is_open()
    assert not breaker.is_closed()
    assert breaker.state == CircuitBreakerState.OPEN


@pytest.mark.unit
def test_circuit_breaker_success_resets_failures():
    """Test success resets failure counter"""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60)

    # Record 2 failures
    breaker.record_failure()
    breaker.record_failure()

    # Record success
    breaker.record_success()

    # Failure count should be reset
    assert breaker.is_closed()

    # Now 3 more failures should be needed to open
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_closed()  # Still closed

    breaker.record_failure()  # 3rd failure
    assert breaker.is_open()  # Now open


# ============================================================================
# STATE TRANSITION TESTS
# ============================================================================

@pytest.mark.unit
def test_circuit_breaker_open_to_half_open():
    """Test circuit transitions from OPEN to HALF_OPEN after timeout"""
    breaker = CircuitBreaker(failure_threshold=2, timeout=1)  # 1 second timeout

    # Open the circuit
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open()

    # Wait for timeout
    time.sleep(1.1)

    # Check state - should transition to HALF_OPEN
    assert not breaker.is_open()  # is_open() triggers transition
    assert breaker.is_half_open()


@pytest.mark.unit
def test_circuit_breaker_half_open_to_closed_on_success():
    """Test circuit transitions from HALF_OPEN to CLOSED on success"""
    breaker = CircuitBreaker(failure_threshold=2, timeout=1, half_open_max_calls=1)

    # Open the circuit
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open()

    # Wait for timeout to transition to HALF_OPEN
    time.sleep(1.1)
    assert not breaker.is_open()
    assert breaker.is_half_open()

    # Record success in HALF_OPEN state
    breaker.record_success()

    # Should transition to CLOSED
    assert breaker.is_closed()
    assert not breaker.is_half_open()


@pytest.mark.unit
def test_circuit_breaker_half_open_to_open_on_failure():
    """Test circuit transitions from HALF_OPEN back to OPEN on failure"""
    breaker = CircuitBreaker(failure_threshold=2, timeout=1, half_open_max_calls=1)

    # Open the circuit
    breaker.record_failure()
    breaker.record_failure()

    # Wait for timeout
    time.sleep(1.1)
    assert not breaker.is_open()
    assert breaker.is_half_open()

    # Record failure in HALF_OPEN state
    breaker.record_failure()

    # Should transition back to OPEN
    assert breaker.is_open()
    assert not breaker.is_half_open()


# ============================================================================
# TIMEOUT BEHAVIOR TESTS
# ============================================================================

@pytest.mark.unit
def test_circuit_breaker_blocks_while_open():
    """Test circuit blocks requests while OPEN (before timeout)"""
    breaker = CircuitBreaker(failure_threshold=2, timeout=60)

    # Open the circuit
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open()

    # Should block requests
    assert breaker.is_open()
    time.sleep(0.1)
    assert breaker.is_open()  # Still open (timeout not reached)


@pytest.mark.unit
def test_circuit_breaker_custom_timeout():
    """Test circuit uses custom timeout value"""
    breaker = CircuitBreaker(failure_threshold=2, timeout=2)  # 2 second timeout

    # Open the circuit
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open()

    # Wait 1 second - should still be open
    time.sleep(1.0)
    assert breaker.is_open()

    # Wait another 1.1 seconds - should transition to HALF_OPEN
    time.sleep(1.1)
    assert not breaker.is_open()
    assert breaker.is_half_open()


# ============================================================================
# HALF_OPEN STATE TESTS
# ============================================================================

@pytest.mark.unit
def test_circuit_breaker_half_open_max_calls():
    """Test HALF_OPEN state enforces max_calls limit"""
    breaker = CircuitBreaker(failure_threshold=2, timeout=1, half_open_max_calls=1)

    # Open the circuit
    breaker.record_failure()
    breaker.record_failure()

    # Wait for timeout
    time.sleep(1.1)
    assert breaker.is_half_open()

    # First call should be allowed
    assert not breaker.is_open()

    # But if we check again without recording success, it should block
    # (because max_calls=1 and we've made 1 check)
    # Note: is_open() increments call count in HALF_OPEN state
    assert breaker.is_open()  # Blocked after max calls


# ============================================================================
# MANUAL RESET TESTS
# ============================================================================

@pytest.mark.unit
def test_circuit_breaker_manual_reset():
    """Test circuit can be manually reset"""
    breaker = CircuitBreaker(failure_threshold=2, timeout=60)

    # Open the circuit
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open()

    # Manually reset
    breaker.reset()

    # Should be CLOSED now
    assert breaker.is_closed()
    assert not breaker.is_open()


@pytest.mark.unit
def test_circuit_breaker_reset_clears_failure_count():
    """Test reset clears failure counter"""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60)

    # Record 2 failures
    breaker.record_failure()
    breaker.record_failure()

    # Reset
    breaker.reset()

    # Should need 3 failures to open (not 1)
    breaker.record_failure()
    assert breaker.is_closed()

    breaker.record_failure()
    assert breaker.is_closed()

    breaker.record_failure()  # 3rd failure
    assert breaker.is_open()


# ============================================================================
# STATUS REPORTING TESTS
# ============================================================================

@pytest.mark.unit
def test_circuit_breaker_get_status():
    """Test get_status returns correct information"""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60)

    status = breaker.get_status()

    assert status["state"] == CircuitBreakerState.CLOSED
    assert status["failure_count"] == 0
    assert status["failure_threshold"] == 3
    assert status["last_failure"] is None
    assert status["timeout_seconds"] == 60


@pytest.mark.unit
def test_circuit_breaker_status_after_failures():
    """Test status reflects failures"""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60)

    breaker.record_failure()
    breaker.record_failure()

    status = breaker.get_status()

    assert status["state"] == CircuitBreakerState.CLOSED
    assert status["failure_count"] == 2
    assert status["last_failure"] is not None


@pytest.mark.unit
def test_circuit_breaker_status_when_open():
    """Test status when circuit is OPEN"""
    breaker = CircuitBreaker(failure_threshold=2, timeout=60)

    breaker.record_failure()
    breaker.record_failure()

    status = breaker.get_status()

    assert status["state"] == CircuitBreakerState.OPEN
    assert status["failure_count"] == 2
    assert status["last_failure"] is not None


# ============================================================================
# EDGE CASES
# ============================================================================

@pytest.mark.unit
def test_circuit_breaker_zero_failure_threshold():
    """Test circuit with very low failure threshold"""
    breaker = CircuitBreaker(failure_threshold=1, timeout=60)

    # Single failure should open circuit
    breaker.record_failure()

    assert breaker.is_open()


@pytest.mark.unit
def test_circuit_breaker_many_consecutive_successes():
    """Test many consecutive successes keep circuit CLOSED"""
    breaker = CircuitBreaker(failure_threshold=3, timeout=60)

    # Record many successes
    for _ in range(100):
        breaker.record_success()

    # Should still be CLOSED
    assert breaker.is_closed()

    # And should still need 3 failures to open
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_closed()

    breaker.record_failure()
    assert breaker.is_open()


@pytest.mark.unit
def test_circuit_breaker_success_in_open_state():
    """Test recording success in OPEN state (edge case)"""
    breaker = CircuitBreaker(failure_threshold=2, timeout=60)

    # Open the circuit
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.is_open()

    # Record success (shouldn't happen in practice, but should handle gracefully)
    breaker.record_success()

    # Should transition to CLOSED
    assert breaker.is_closed()


# ============================================================================
# THREAD SAFETY TESTS (basic)
# ============================================================================

@pytest.mark.unit
def test_circuit_breaker_concurrent_access():
    """Test circuit breaker handles concurrent access"""
    import threading

    breaker = CircuitBreaker(failure_threshold=10, timeout=60)
    failures_recorded = []

    def record_failures():
        for _ in range(5):
            breaker.record_failure()
            failures_recorded.append(1)

    # Create multiple threads
    threads = [threading.Thread(target=record_failures) for _ in range(3)]

    # Start all threads
    for thread in threads:
        thread.start()

    # Wait for completion
    for thread in threads:
        thread.join()

    # Should have recorded 15 failures total (3 threads x 5 failures)
    assert len(failures_recorded) == 15

    # Circuit should be OPEN (threshold is 10)
    assert breaker.is_open()
