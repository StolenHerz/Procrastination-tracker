"""Фоновый таймер интервальных проверок."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_MINUTES = 25

_POLL_SECONDS = 0.1
_JOIN_TIMEOUT_SECONDS = 2.0


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


class Timer:
    """Потокобезопасный таймер с фоновым потоком."""

    def __init__(self, interval_minutes: float = DEFAULT_INTERVAL_MINUTES) -> None:
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._state = TimerState.IDLE
        self._interval_minutes = float(interval_minutes)
        self._remaining_seconds = self._interval_minutes * 60
        self._deadline: float | None = None

    def _ensure_thread(self) -> None:
        """Запустить фоновый поток, если он ещё не работает."""
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="timer",
            daemon=True,
        )
        self._thread.start()
        logger.debug("Фоновый поток таймера запущен.")

    def _run(self) -> None:
        """Ожидать события таймера, не затрагивая Tkinter."""
        while not self._stop_event.is_set():
            self._wake_event.wait(_POLL_SECONDS)
            self._wake_event.clear()
            if self._stop_event.is_set():
                break
            self._tick()

    def _tick(self) -> None:
        """Обработать один шаг таймера."""
