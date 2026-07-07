"""In-memory circuit breaker for provider resilience."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from time import monotonic
from typing import Callable, Protocol

from src.resilience.contracts import RuntimeResilienceSettings
from src.resilience.exceptions import CircuitOpenError


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitRecord:
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    opened_at: float | None = None
    half_open_active_calls: int = 0


class CircuitStateStore(Protocol):
    def get(self, key: str) -> CircuitRecord: ...
    def set(self, key: str, record: CircuitRecord) -> None: ...


class InMemoryCircuitStateStore:
    def __init__(self) -> None:
        self._records: dict[str, CircuitRecord] = {}

    def get(self, key: str) -> CircuitRecord:
        record = self._records.get(key)
        if record is None:
            record = CircuitRecord()
            self._records[key] = record
        return CircuitRecord(
            state=record.state,
            failure_count=record.failure_count,
            opened_at=record.opened_at,
            half_open_active_calls=record.half_open_active_calls,
        )

    def set(self, key: str, record: CircuitRecord) -> None:
        self._records[key] = CircuitRecord(
            state=record.state,
            failure_count=record.failure_count,
            opened_at=record.opened_at,
            half_open_active_calls=record.half_open_active_calls,
        )

    def clear(self) -> None:
        self._records.clear()


@dataclass(frozen=True)
class CircuitPermit:
    provider_name: str
    state_before: CircuitState


class CircuitBreaker:
    def __init__(
        self,
        settings: RuntimeResilienceSettings,
        *,
        store: CircuitStateStore | None = None,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self.settings = settings
        self.store = store or InMemoryCircuitStateStore()
        self.clock = clock

    def before_call(self, provider_name: str) -> CircuitPermit:
        key = _provider_key(provider_name)
        if not self.settings.circuit_breaker_enabled:
            return CircuitPermit(provider_name=key, state_before=CircuitState.CLOSED)

        record = self.store.get(key)
        now = self.clock()
        if record.state == CircuitState.OPEN:
            opened_at = record.opened_at if record.opened_at is not None else now
            recovery_at = opened_at + self.settings.circuit_breaker_recovery_seconds
            if now < recovery_at:
                raise CircuitOpenError(f"Circuit is open for provider {key}.")
            record.state = CircuitState.HALF_OPEN
            record.half_open_active_calls = 0

        if record.state == CircuitState.HALF_OPEN:
            if record.half_open_active_calls >= self.settings.circuit_breaker_half_open_max_calls:
                self.store.set(key, record)
                raise CircuitOpenError(f"Circuit half-open probe limit reached for provider {key}.")
            record.half_open_active_calls += 1

        self.store.set(key, record)
        return CircuitPermit(provider_name=key, state_before=record.state)

    def record_success(self, provider_name: str) -> CircuitState:
        key = _provider_key(provider_name)
        record = self.store.get(key)
        record.state = CircuitState.CLOSED
        record.failure_count = 0
        record.opened_at = None
        record.half_open_active_calls = 0
        self.store.set(key, record)
        return record.state

    def record_failure(self, provider_name: str, *, transient: bool) -> CircuitState:
        key = _provider_key(provider_name)
        record = self.store.get(key)
        if not self.settings.circuit_breaker_enabled or not transient:
            self.store.set(key, record)
            return record.state

        if record.state == CircuitState.HALF_OPEN:
            record.state = CircuitState.OPEN
            record.opened_at = self.clock()
            record.half_open_active_calls = 0
        else:
            record.failure_count += 1
            if record.failure_count >= self.settings.circuit_breaker_failure_threshold:
                record.state = CircuitState.OPEN
                record.opened_at = self.clock()
                record.half_open_active_calls = 0

        self.store.set(key, record)
        return record.state

    def current_state(self, provider_name: str) -> CircuitState:
        return self.store.get(_provider_key(provider_name)).state


def _provider_key(provider_name: str) -> str:
    return (provider_name or "unknown").strip().lower()


__all__ = [
    "CircuitBreaker",
    "CircuitPermit",
    "CircuitRecord",
    "CircuitState",
    "CircuitStateStore",
    "InMemoryCircuitStateStore",
]
