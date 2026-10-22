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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

DEFAULT_ACTIVITIES: tuple[str, ...] = (
    "Учёба/работа",
    "Прокрастинирую",
    "Отдыхаю",
)

MAX_ACTIVITY_NAME_LENGTH = 50

DEFAULT_INTERVAL_MINUTES = 25
MIN_INTERVAL_MINUTES = 1
MAX_INTERVAL_MINUTES = 1440
INTERVAL_SETTING_KEY = "timer_interval_minutes"


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


@dataclass(frozen=True)
class LogEntry:
    """Одна запись журнала активности."""

    id: int
    activity_id: int
    activity_name: str
    timestamp: datetime


@dataclass(frozen=True)
class ActivityStat:
    """Количество записей по виду деятельности за период."""

    activity_id: int
    activity_name: str
    count: int


def default_db_path() -> Path:
    """Вернуть путь к data.db рядом с приложением или exe."""
    if getattr(sys, "frozen", False):
        base_dir = Path(sys.executable).resolve().parent
    else:
        base_dir = Path(__file__).resolve().parent
    return base_dir / "data.db"


def _normalize_timestamp(value: datetime | None) -> str:
    """Привести время к строке, пригодной для сравнения и сортировки."""
    moment = value or datetime.now()
    return moment.replace(microsecond=0).isoformat(sep=" ")


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

    def log_activity(
        self, activity_id: int, timestamp: datetime | None = None
    ) -> int:
        """Сохранить запись активности и вернуть её id."""
        if self.get_activity(activity_id) is None:
            raise DatabaseError("Вид деятельности не найден.")

        moment = _normalize_timestamp(timestamp)
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO logs (activity_id, timestamp) VALUES (?, ?)",
                (activity_id, moment),
            )
            log_id = int(cursor.lastrowid)

        logger.info("Записана активность %s в %s", activity_id, moment)
        return log_id

    def recent_logs(self, limit: int = 20) -> list[LogEntry]:
        """Последние записи журнала (свежие сверху)."""
        safe_limit = max(1, min(limit, 500))
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT l.id, l.activity_id, l.timestamp, a.name AS activity_name "
                "FROM logs AS l "
                "JOIN activities AS a ON a.id = l.activity_id "
                "ORDER BY l.timestamp DESC, l.id DESC "
                "LIMIT ?",
                (safe_limit,),
            ).fetchall()

        result: list[LogEntry] = []
        for row in rows:
            try:
                moment = datetime.fromisoformat(row["timestamp"])
            except ValueError:
                logger.warning("Некорректная дата в записи %s", row["id"])
                continue
            result.append(
                LogEntry(
                    id=row["id"],
                    activity_id=row["activity_id"],
                    activity_name=row["activity_name"],
                    timestamp=moment,
                )
            )
        return result

    # ------------------------------------------------------------------
    # Статистика
    # ------------------------------------------------------------------

    def activity_totals(self, days: int = 7) -> list[ActivityStat]:
        """Суммарное количество записей по каждому виду за последние days дней."""
        since = self._period_start(days)
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT a.id AS activity_id, a.name AS activity_name, "
                "       COUNT(l.id) AS total "
                "FROM activities AS a "
                "LEFT JOIN logs AS l "
                "       ON l.activity_id = a.id AND l.timestamp >= ? "
                "GROUP BY a.id, a.name "
                "ORDER BY total DESC, a.name COLLATE NOCASE",
                (since,),
            ).fetchall()

        return [
            ActivityStat(
                activity_id=row["activity_id"],
                activity_name=row["activity_name"],
                count=int(row["total"]),
            )
            for row in rows
        ]

    def daily_totals(self, days: int = 7) -> dict[date, int]:
        """Количество записей по дням, включая дни без активности."""
        safe_days = max(1, min(days, 365))
        since_date = date.today() - timedelta(days=safe_days - 1)

        with self._connect() as connection:
            rows = connection.execute(
                "SELECT date(timestamp) AS day, COUNT(*) AS total "
                "FROM logs WHERE timestamp >= ? "
                "GROUP BY day",
                (f"{since_date.isoformat()} 00:00:00",),
            ).fetchall()

        counts = {row["day"]: int(row["total"]) for row in rows}
        result: dict[date, int] = {}
        for offset in range(safe_days):
            day = since_date + timedelta(days=offset)
            result[day] = counts.get(day.isoformat(), 0)
        return result

    def _period_start(self, days: int) -> str:
        safe_days = max(1, min(days, 365))
        start = date.today() - timedelta(days=safe_days - 1)
        return f"{start.isoformat()} 00:00:00"

    # ------------------------------------------------------------------
    # Настройки
    # ------------------------------------------------------------------

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_interval_minutes(self) -> int:
        """Интервал таймера в минутах (25 по умолчанию)."""
        raw_value = self.get_setting(INTERVAL_SETTING_KEY)
        try:
            minutes = (
                int(raw_value) if raw_value is not None else DEFAULT_INTERVAL_MINUTES
            )
        except (TypeError, ValueError):
            logger.warning("Некорректный интервал в настройках: %r", raw_value)
            return DEFAULT_INTERVAL_MINUTES

        return max(MIN_INTERVAL_MINUTES, min(minutes, MAX_INTERVAL_MINUTES))

    def set_interval_minutes(self, minutes: int) -> None:
        if isinstance(minutes, bool) or not isinstance(minutes, int):
            raise DatabaseError("Интервал должен быть целым числом минут.")
        if not MIN_INTERVAL_MINUTES <= minutes <= MAX_INTERVAL_MINUTES:
            raise DatabaseError(
                f"Интервал должен быть от {MIN_INTERVAL_MINUTES} "
                f"до {MAX_INTERVAL_MINUTES} минут."
            )
        self.set_setting(INTERVAL_SETTING_KEY, str(minutes))


if __name__ == "__main__":
    # Быстрая самопроверка модуля на временной базе данных.
    import tempfile

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    with tempfile.TemporaryDirectory() as tmp_dir:
        db = Database(Path(tmp_dir) / "data.db")

        print("Виды деятельности:")
        activities = db.list_activities()
        for item in activities:
            print(f"  {item.id}: {item.name} (default={item.is_default})")

        db.log_activity(activities[0].id)
        db.log_activity(activities[1].id)

        print("\nСтатистика за 7 дней:")
        for stat in db.activity_totals(7):
            print(f"  {stat.activity_name}: {stat.count}")

        print("\nЗаписи по дням:")
        for day, count in db.daily_totals(7).items():
            print(f"  {day}: {count}")

        db.set_interval_minutes(30)
        print(f"\nИнтервал: {db.get_interval_minutes()} мин.")
        print("Самопроверка завершена успешно.")
