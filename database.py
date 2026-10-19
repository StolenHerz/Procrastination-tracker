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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

DEFAULT_ACTIVITIES: tuple[str, ...] = (
    "Учёба/работа",
    "Прокрастинирую",
    "Отдыхаю",
)

MAX_ACTIVITY_NAME_LENGTH = 50


class DatabaseError(RuntimeError):
    """Ошибка при работе с базой данных."""


class ActivityExistsError(DatabaseError):
    """Вид деятельности с таким названием уже существует."""


@dataclass(frozen=True)
class Activity:
    """Вид деятельности."""

    id: int
    name: str
    is_default: bool


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

    @staticmethod
    def _row_to_activity(row: sqlite3.Row) -> Activity:
        return Activity(
            id=row["id"],
            name=row["name"],
            is_default=bool(row["is_default"]),
        )

    def list_activities(self) -> list[Activity]:
        """Вернуть все виды деятельности, сначала стандартные."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT id, name, is_default FROM activities "
                "ORDER BY is_default DESC, name COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_activity(row) for row in rows]

    def get_activity(self, activity_id: int) -> Activity | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id, name, is_default FROM activities WHERE id = ?",
                (activity_id,),
            ).fetchone()
        return self._row_to_activity(row) if row else None

    @staticmethod
    def _validate_activity_name(name: str) -> str:
        cleaned = " ".join(name.split())
        if not cleaned:
            raise DatabaseError("Название вида деятельности не может быть пустым.")
        if len(cleaned) > MAX_ACTIVITY_NAME_LENGTH:
            raise DatabaseError(
                f"Название не должно превышать {MAX_ACTIVITY_NAME_LENGTH} символов."
            )
        return cleaned

    def _ensure_name_is_free(self, name: str, exclude_id: int | None = None) -> None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT id FROM activities WHERE name = ? COLLATE NOCASE",
                (name,),
            ).fetchone()

        if row is not None and row["id"] != exclude_id:
            raise ActivityExistsError(
                "Вид деятельности с таким названием уже существует."
            )

    def add_activity(self, name: str) -> Activity:
        """Добавить пользовательский вид деятельности."""
        cleaned = self._validate_activity_name(name)
        self._ensure_name_is_free(cleaned)

        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO activities (name, is_default) VALUES (?, 0)",
                (cleaned,),
            )
            activity_id = int(cursor.lastrowid)

        logger.info("Добавлен вид деятельности: %s", cleaned)
        return Activity(id=activity_id, name=cleaned, is_default=False)

    def rename_activity(self, activity_id: int, new_name: str) -> Activity:
        """Переименовать любой вид деятельности, сохранив флаг is_default."""
        cleaned = self._validate_activity_name(new_name)
        current = self.get_activity(activity_id)
        if current is None:
            raise DatabaseError("Вид деятельности не найден.")

        self._ensure_name_is_free(cleaned, exclude_id=activity_id)

        with self._connect() as connection:
            connection.execute(
                "UPDATE activities SET name = ? WHERE id = ?",
                (cleaned, activity_id),
            )

        logger.info("Вид деятельности %s переименован в %s", activity_id, cleaned)
        return Activity(id=activity_id, name=cleaned, is_default=current.is_default)

    def delete_activity(self, activity_id: int) -> None:
        """Удалить пользовательский вид деятельности без записей в журнале."""
        activity = self.get_activity(activity_id)
        if activity is None:
            raise DatabaseError("Вид деятельности не найден.")
        if activity.is_default:
            raise DatabaseError("Стандартный вид деятельности нельзя удалить.")

        with self._connect() as connection:
            logs_count = connection.execute(
                "SELECT COUNT(*) AS total FROM logs WHERE activity_id = ?",
                (activity_id,),
            ).fetchone()["total"]
            if logs_count:
                raise DatabaseError(
                    "Нельзя удалить вид деятельности, по которому уже есть записи."
                )

            connection.execute(
                "DELETE FROM activities WHERE id = ?",
                (activity_id,),
            )

        logger.info("Удалён вид деятельности: %s", activity.name)

    # ------------------------------------------------------------------
    # Журнал активности
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Статистика
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Настройки
    # ------------------------------------------------------------------
