"""Общая фикстура тестов: временная база данных на время одного теста."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from database import Database


class TempDatabaseTestCase(unittest.TestCase):
    """Базовый тест, создающий отдельную БД во временной папке."""

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp_dir.cleanup)
        self.db_path = Path(self._tmp_dir.name) / "data.db"
        self.db = Database(self.db_path)
