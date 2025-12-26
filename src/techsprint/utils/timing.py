from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterator, List


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class StepTiming:
    name: str
    started_at: datetime
    finished_at: datetime

    @property
    def duration_s(self) -> float:
        return (self.finished_at - self.started_at).total_seconds()


class StepTimer:
    def __init__(self, *, clock: Clock = utc_now) -> None:
        self._clock = clock
        self.steps: List[StepTiming] = []

    @property
    def clock(self) -> Clock:
        return self._clock

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        started_at = self._clock()
        try:
            yield
        finally:
            finished_at = self._clock()
            self.steps.append(
                StepTiming(
                    name=name,
                    started_at=started_at,
                    finished_at=finished_at,
                )
            )
