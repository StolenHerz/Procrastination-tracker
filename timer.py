"""Фоновый таймер интервальных проверок."""

from __future__ import annotations

import logging
import threading
import time
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
        with self._lock:
            if self._state is not TimerState.RUNNING or self._deadline is None:
                return

            remaining = self._deadline - time.monotonic()
            if remaining > 0:
                self._remaining_seconds = remaining
                return

            self._remaining_seconds = 0.0
            self._state = TimerState.IDLE
            self._deadline = None

        logger.info("Интервал таймера истёк.")

    def start(self) -> None:
        """Запустить отсчёт с полного интервала."""
        with self._lock:
            if self._state is TimerState.RUNNING:
                return

            self._ensure_thread()
            self._state = TimerState.RUNNING
            self._remaining_seconds = self._interval_minutes * 60
            self._deadline = time.monotonic() + self._remaining_seconds
            self._wake_event.set()

        logger.info("Таймер запущен на %.2f мин.", self._interval_minutes)

    def stop(self) -> None:
        """Остановить таймер и завершить фоновый поток."""
        with self._lock:
            self._stop_event.set()
            self._wake_event.set()
            thread = self._thread
            self._state = TimerState.IDLE
            self._deadline = None
            self._remaining_seconds = self._interval_minutes * 60

        if thread is not None and thread.is_alive():
            thread.join(timeout=_JOIN_TIMEOUT_SECONDS)
            if thread.is_alive():
                logger.warning(
                    "Фоновый поток таймера не завершился за %.1f с.",
                    _JOIN_TIMEOUT_SECONDS,
                )

        with self._lock:
            if self._thread is thread:
                self._thread = None

        logger.info("Таймер остановлен.")

    def reset(self) -> None:
        """Сбросить отсчёт на полный интервал."""
        with self._lock:
            self._remaining_seconds = self._interval_minutes * 60
            if self._state is TimerState.RUNNING:
                self._deadline = time.monotonic() + self._remaining_seconds
            else:
                self._deadline = None
            self._wake_event.set()

        logger.info("Таймер сброшен.")

    def snapshot(self) -> TimerSnapshot:
        """Вернуть согласованный снимок состояния."""
        with self._lock:
            remaining = self._remaining_seconds
            if self._state is TimerState.RUNNING and self._deadline is not None:
                remaining = max(0.0, self._deadline - time.monotonic())
            return TimerSnapshot(
                state=self._state,
                interval_minutes=self._interval_minutes,
                remaining_seconds=remaining,
            )
