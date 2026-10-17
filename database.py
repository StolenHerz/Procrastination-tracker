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

DEFAULT_ACTIVITIES: tuple[str, ...] = (
    "Учёба/работа",
    "Прокрастинирую",
    "Отдыхаю",
)


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


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS activities (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1))
);

CREATE TABLE IF NOT EXISTS logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id INTEGER NOT NULL,
    timestamp   TEXT    NOT NULL,
    FOREIGN KEY (activity_id) REFERENCES activities (id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs (timestamp);
CREATE INDEX IF NOT EXISTS idx_logs_activity_id ON logs (activity_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


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
        self._init_schema()
        self._seed_default_activities()

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

    def _init_schema(self) -> None:
        try:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.executescript(_SCHEMA_SQL)
        except DatabaseError:
            raise
        except OSError as exc:
            raise DatabaseError(
                f"Нет доступа к файлу базы данных: {self._db_path}"
            ) from exc

    def _seed_default_activities(self) -> None:
        """Добавить стандартные виды деятельности только при пустой таблице."""
        with self._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) AS total FROM activities"
            ).fetchone()["total"]
            if count:
                return

            connection.executemany(
                "INSERT INTO activities (name, is_default) VALUES (?, 1)",
                [(name,) for name in DEFAULT_ACTIVITIES],
            )
            logger.info("Добавлены стандартные виды деятельности.")

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
