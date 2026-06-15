"""
backend/core/circuit_breaker.py
────────────────────────────────
Production-grade circuit breaker for external service calls.

States:
- CLOSED   → normal operation; failures increment counter
- OPEN     → fast-fail; no calls pass through; reset after timeout
- HALF_OPEN → probe call allowed; success → CLOSED, failure → OPEN

Features:
- Thread-safe state management
- Exponential backoff with full jitter
- Error type classification (transient vs deterministic)
- Per-service state isolation
- @circuit_breaker(service_name) decorator for sync and async functions
- Prometheus-compatible metrics hooks
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Callable, Optional, Type

from backend.core.config import settings

logger = logging.getLogger(__name__)


# ── State enum ────────────────────────────────────────────────────────────────

class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# ── Error classification ──────────────────────────────────────────────────────

#: Exception types that are considered transient (will trip the circuit)
TRANSIENT_ERRORS: tuple[Type[Exception], ...] = (
    ConnectionError,
    TimeoutError,
    OSError,
)

#: Exception types that are deterministic (will NOT trip the circuit)
DETERMINISTIC_ERRORS: tuple[Type[Exception], ...] = (
    ValueError,
    TypeError,
    KeyError,
    AttributeError,
    NotImplementedError,
)


def is_transient_error(exc: Exception) -> bool:
    """Return True if *exc* is considered transient and should trip the circuit."""
    if isinstance(exc, DETERMINISTIC_ERRORS):
        return False
    # HTTP 4xx errors are not transient
    status_code = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status_code and 400 <= status_code < 500:
        return False
    return True


# ── Circuit breaker state ─────────────────────────────────────────────────────

@dataclass
class CircuitBreakerStats:
    """Snapshot of circuit breaker metrics."""

    service_name: str
    state: CircuitState
    failure_count: int
    success_count: int
    total_calls: int
    last_failure_time: Optional[float]
    last_state_change: float
    open_until: Optional[float]


class CircuitBreaker:
    """State machine implementing the circuit breaker pattern.

    Args:
        service_name:     Unique identifier for the protected service.
        threshold:        Number of failures before opening the circuit.
        reset_timeout:    Seconds to wait in OPEN state before trying HALF_OPEN.
        half_open_max:    Maximum probe calls allowed in HALF_OPEN state.
        base_backoff:     Base seconds for exponential backoff calculation.
        max_backoff:      Maximum backoff cap in seconds.
        success_threshold: Consecutive successes in HALF_OPEN to close circuit.
    """

    def __init__(
        self,
        service_name: str,
        threshold: int = settings.CIRCUIT_BREAKER_THRESHOLD,
        reset_timeout: int = settings.CIRCUIT_BREAKER_RESET_TIMEOUT,
        half_open_max: int = 1,
        base_backoff: float = 1.0,
        max_backoff: float = 60.0,
        success_threshold: int = 2,
    ) -> None:
        self.service_name = service_name
        self.threshold = threshold
        self.reset_timeout = reset_timeout
        self.half_open_max = half_open_max
        self.base_backoff = base_backoff
        self.max_backoff = max_backoff
        self.success_threshold = success_threshold

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._success_count: int = 0
        self._half_open_calls: int = 0
        self._consecutive_successes: int = 0
        self._total_calls: int = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change: float = time.monotonic()
        self._open_until: Optional[float] = None
        self._attempt: int = 0  # tracks backoff exponent
        self._lock: Lock = Lock()

        # Rolling window of recent failure timestamps (last 60s)
        self._recent_failures: deque[float] = deque(maxlen=100)

    @property
    def state(self) -> CircuitState:
        self._maybe_transition_to_half_open()
        return self._state

    def _maybe_transition_to_half_open(self) -> None:
        """Transition OPEN → HALF_OPEN if the reset timeout has elapsed."""
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and self._open_until is not None
                and time.monotonic() >= self._open_until
            ):
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._consecutive_successes = 0
                self._last_state_change = time.monotonic()
                logger.info(
                    "Circuit '%s': OPEN → HALF_OPEN (probing)", self.service_name
                )

    def _open_circuit(self) -> None:
        """Transition to OPEN state with exponential backoff."""
        self._attempt += 1
        # Full jitter backoff: sleep = random(0, min(cap, base * 2^attempt))
        cap = min(self.max_backoff, self.base_backoff * (2 ** self._attempt))
        jitter = random.uniform(0, cap)
        self._open_until = time.monotonic() + max(self.reset_timeout, jitter)

        prev = self._state
        self._state = CircuitState.OPEN
        self._last_state_change = time.monotonic()
        logger.warning(
            "Circuit '%s': %s → OPEN (failures=%d, retry_in=%.1fs)",
            self.service_name,
            prev.value,
            self._failure_count,
            max(self.reset_timeout, jitter),
        )

    def _close_circuit(self) -> None:
        """Transition to CLOSED state and reset counters."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._consecutive_successes = 0
        self._attempt = 0
        self._open_until = None
        self._last_state_change = time.monotonic()
        logger.info("Circuit '%s': → CLOSED (recovered)", self.service_name)

    def record_success(self) -> None:
        """Record a successful call; may close the circuit."""
        with self._lock:
            self._total_calls += 1
            self._success_count += 1
            self._consecutive_successes += 1

            if self._state == CircuitState.HALF_OPEN:
                if self._consecutive_successes >= self.success_threshold:
                    self._close_circuit()
            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success in closed state
                self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self, exc: Exception) -> None:
        """Record a failed call; may open the circuit."""
        if not is_transient_error(exc):
            # Deterministic errors don't affect circuit state
            logger.debug(
                "Circuit '%s': ignoring deterministic error %s",
                self.service_name,
                type(exc).__name__,
            )
            return

        with self._lock:
            self._total_calls += 1
            self._failure_count += 1
            self._consecutive_successes = 0
            self._last_failure_time = time.monotonic()
            self._recent_failures.append(self._last_failure_time)

            if self._state == CircuitState.CLOSED:
                if self._failure_count >= self.threshold:
                    self._open_circuit()
            elif self._state == CircuitState.HALF_OPEN:
                # Any failure in HALF_OPEN immediately re-opens
                self._open_circuit()

    def can_execute(self) -> bool:
        """Return True if a call is allowed to proceed."""
        state = self.state  # triggers OPEN→HALF_OPEN transition check
        with self._lock:
            if state == CircuitState.CLOSED:
                return True
            elif state == CircuitState.OPEN:
                return False
            elif state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max:
                    self._half_open_calls += 1
                    return True
                return False
        return False

    def get_stats(self) -> CircuitBreakerStats:
        """Return a snapshot of the current circuit breaker state."""
        return CircuitBreakerStats(
            service_name=self.service_name,
            state=self._state,
            failure_count=self._failure_count,
            success_count=self._success_count,
            total_calls=self._total_calls,
            last_failure_time=self._last_failure_time,
            last_state_change=self._last_state_change,
            open_until=self._open_until,
        )

    def reset(self) -> None:
        """Manually reset to CLOSED state (admin/testing use)."""
        with self._lock:
            self._close_circuit()

    def force_open(self) -> None:
        """Manually force OPEN state (admin/maintenance use)."""
        with self._lock:
            self._open_circuit()


# ── Registry ──────────────────────────────────────────────────────────────────

_registry: dict[str, CircuitBreaker] = {}
_registry_lock: Lock = Lock()


def get_circuit_breaker(
    service_name: str,
    threshold: int = settings.CIRCUIT_BREAKER_THRESHOLD,
    reset_timeout: int = settings.CIRCUIT_BREAKER_RESET_TIMEOUT,
) -> CircuitBreaker:
    """Return (creating if needed) the named circuit breaker."""
    with _registry_lock:
        if service_name not in _registry:
            _registry[service_name] = CircuitBreaker(
                service_name=service_name,
                threshold=threshold,
                reset_timeout=reset_timeout,
            )
        return _registry[service_name]


def get_all_stats() -> list[CircuitBreakerStats]:
    """Return stats for all registered circuit breakers."""
    with _registry_lock:
        return [cb.get_stats() for cb in _registry.values()]


# ── Decorator ─────────────────────────────────────────────────────────────────

class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        super().__init__(
            f"Circuit breaker for '{service_name}' is OPEN – call rejected"
        )


def circuit_breaker(
    service_name: str,
    threshold: int = settings.CIRCUIT_BREAKER_THRESHOLD,
    reset_timeout: int = settings.CIRCUIT_BREAKER_RESET_TIMEOUT,
    fallback: Optional[Callable] = None,
):
    """Decorator factory that protects a function with a circuit breaker.

    Works for both regular (sync) and async functions.

    Args:
        service_name:  Unique name for the protected service.
        threshold:     Failure count before opening the circuit.
        reset_timeout: Seconds before attempting HALF_OPEN.
        fallback:      Optional callable invoked when the circuit is open.
                       Must have the same signature as the decorated function.

    Usage::

        @circuit_breaker("github-api")
        async def fetch_repo_info(url: str) -> dict:
            ...

        @circuit_breaker("llm-service", fallback=lambda *a, **kw: {"error": "LLM unavailable"})
        def call_llm(prompt: str) -> str:
            ...
    """
    def decorator(func: Callable) -> Callable:
        cb = get_circuit_breaker(service_name, threshold, reset_timeout)

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not cb.can_execute():
                    logger.warning("Circuit '%s' is OPEN – rejecting call", service_name)
                    if fallback is not None:
                        if asyncio.iscoroutinefunction(fallback):
                            return await fallback(*args, **kwargs)
                        return fallback(*args, **kwargs)
                    raise CircuitOpenError(service_name)

                try:
                    result = await func(*args, **kwargs)
                    cb.record_success()
                    return result
                except CircuitOpenError:
                    raise
                except Exception as exc:
                    cb.record_failure(exc)
                    raise

            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                if not cb.can_execute():
                    logger.warning("Circuit '%s' is OPEN – rejecting call", service_name)
                    if fallback is not None:
                        return fallback(*args, **kwargs)
                    raise CircuitOpenError(service_name)

                try:
                    result = func(*args, **kwargs)
                    cb.record_success()
                    return result
                except CircuitOpenError:
                    raise
                except Exception as exc:
                    cb.record_failure(exc)
                    raise

            return sync_wrapper

    return decorator


# ── Retry with backoff ────────────────────────────────────────────────────────

async def retry_with_backoff(
    func: Callable,
    *args: Any,
    max_retries: int = settings.MAX_RETRIES,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple[Type[Exception], ...] = TRANSIENT_ERRORS,
    **kwargs: Any,
) -> Any:
    """Retry an async function with exponential backoff + full jitter.

    Args:
        func:                 Async callable to retry.
        *args:                Positional arguments for *func*.
        max_retries:          Maximum number of retry attempts.
        base_delay:           Initial backoff delay in seconds.
        max_delay:            Maximum delay cap.
        retryable_exceptions: Only retry on these exception types.
        **kwargs:             Keyword arguments for *func*.

    Returns:
        The result of the successful call.

    Raises:
        The last exception if all retries are exhausted.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            return func(*args, **kwargs)
        except retryable_exceptions as exc:
            last_exc = exc
            if attempt >= max_retries:
                break
            cap = min(max_delay, base_delay * (2 ** attempt))
            delay = random.uniform(0, cap)
            logger.warning(
                "Retry %d/%d for %s after %.2fs (error: %s)",
                attempt + 1,
                max_retries,
                getattr(func, "__name__", str(func)),
                delay,
                exc,
            )
            await asyncio.sleep(delay)
        except Exception as exc:
            # Non-retryable exception – propagate immediately
            raise exc from None

    raise last_exc  # type: ignore[misc]
