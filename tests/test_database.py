"""Базовые тесты временной базы данных."""

from __future__ import annotations

from tests.db_test_case import TempDatabaseTestCase


class TempDatabaseTest(TempDatabaseTestCase):
    def test_database_file_is_created(self) -> None:
        self.assertTrue(self.db_path.exists())
        self.assertEqual(self.db.path, self.db_path)
