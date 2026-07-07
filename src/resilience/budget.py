"""Deadline budget helpers for runtime timeout propagation."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Callable


@dataclass(frozen=True)
class DeadlineBudget:
    started_at: float
    deadline_at: float
    clock: Callable[[], float] = field(default=monotonic, compare=False, repr=False)

    @classmethod
    def from_timeout(
        cls,
        timeout_seconds: float,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> "DeadlineBudget":
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        started_at = clock()
        return cls(started_at=started_at, deadline_at=started_at + timeout_seconds, clock=clock)

    def elapsed_seconds(self) -> float:
        return max(0.0, self.clock() - self.started_at)

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_at - self.clock())

    def cap_timeout(self, configured_timeout: float) -> float:
        if configured_timeout <= 0:
            raise ValueError("configured_timeout must be > 0")
        remaining = self.remaining_seconds()
        if remaining <= 0:
            return 0.0
        return min(configured_timeout, remaining)

    def expired(self) -> bool:
        return self.remaining_seconds() <= 0


__all__ = ["DeadlineBudget"]
