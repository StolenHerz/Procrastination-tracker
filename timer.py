"""Фоновый таймер интервальных проверок."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

DEFAULT_INTERVAL_MINUTES = 25


class TimerState(str, Enum):
    """Состояние таймера."""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass(frozen=True)
class TimerSnapshot:
    """Неизменяемый снимок состояния таймера."""

    state: TimerState
    interval_minutes: float
    remaining_seconds: float
