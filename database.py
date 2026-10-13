"""Слой работы с базой данных SQLite.

Модуль инкапсулирует создание схемы, работу с видами деятельности,
логами и настройками. Каждый публичный метод открывает собственное
соединение, поэтому модуль безопасно использовать из разных потоков
(таймер в трее и UI работают параллельно).
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    """Ошибка при работе с базой данных."""


class ActivityExistsError(DatabaseError):
    """Вид деятельности с таким названием уже существует."""


def default_db_path() -> Path:
    """Вернуть путь к data.db рядом с приложением или exe."""
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent
    return base_dir / "data.db"


class Database:
    """Высокоуровневый интерфейс к SQLite-базе приложения."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db_path = Path(db_path) if db_path is not None else default_db_path()

        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DatabaseError(
                f"Не удалось создать папку для базы данных: {self._db_path.parent}"
            ) from exc

        logger.debug("Используется база данных: %s", self._db_path)

    @property
    def path(self) -> Path:
        return self._db_path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """Открыть соединение, гарантированно закрыв его после работы."""
        try:
            connection = sqlite3.connect(str(self._db_path), timeout=30.0)
        except sqlite3.Error as exc:
            raise DatabaseError("Не удалось открыть базу данных.") from exc

        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            logger.exception("Ошибка SQL при работе с %s", self._db_path)
            raise DatabaseError(f"Ошибка базы данных: {exc}") from exc
        finally:
            connection.close()

    # ------------------------------------------------------------------
    # Схема базы данных
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Виды деятельности
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Журнал активности
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Статистика
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Настройки
    # ------------------------------------------------------------------
