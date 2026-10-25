"""Тесты схемы базы данных и стандартных активностей."""

from __future__ import annotations

import sqlite3
from contextlib import closing

from database import DEFAULT_ACTIVITIES, Database
from tests.db_test_case import TempDatabaseTestCase


class SchemaTest(TempDatabaseTestCase):
    def test_expected_tables_and_indexes_exist(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            names = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master")
            }

        self.assertTrue({"activities", "logs", "settings"} <= names)
        self.assertIn("idx_logs_timestamp", names)
        self.assertIn("idx_logs_activity_id", names)

    def test_database_uses_wal_mode(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as connection:
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

        self.assertEqual(mode.lower(), "wal")

    def test_default_activities_are_seeded(self) -> None:
        activities = self.db.list_activities()

        self.assertEqual(
            {activity.name for activity in activities},
            set(DEFAULT_ACTIVITIES),
        )
        self.assertTrue(all(activity.is_default for activity in activities))

    def test_reinitialization_does_not_duplicate_defaults(self) -> None:
        Database(self.db_path)
        Database(self.db_path)

        self.assertEqual(len(self.db.list_activities()), len(DEFAULT_ACTIVITIES))
