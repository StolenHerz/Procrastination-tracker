"""Тесты CRUD и валидации видов деятельности."""

from __future__ import annotations

from database import (
    MAX_ACTIVITY_NAME_LENGTH,
    ActivityExistsError,
    DatabaseError,
)
from tests.db_test_case import TempDatabaseTestCase


class ActivityCrudTest(TempDatabaseTestCase):
    def test_add_activity_creates_custom_activity(self) -> None:
        activity = self.db.add_activity("Читаю")

        self.assertFalse(activity.is_default)
        self.assertEqual(activity.name, "Читаю")
        self.assertEqual(self.db.get_activity(activity.id), activity)
        self.assertIn(activity, self.db.list_activities())

    def test_default_activities_come_first(self) -> None:
        activity = self.db.add_activity("Активность")

        activities = self.db.list_activities()
        self.assertTrue(all(item.is_default for item in activities[:3]))
        self.assertIn(activity, activities[3:])

    def test_duplicate_name_is_case_insensitive(self) -> None:
        existing = self.db.list_activities()[0]

        with self.assertRaises(ActivityExistsError):
            self.db.add_activity(existing.name.upper())

    def test_empty_name_is_rejected(self) -> None:
        for name in ("", "   ", "\t\n"):
            with self.assertRaises(DatabaseError):
                self.db.add_activity(name)

    def test_name_is_trimmed_and_collapsed(self) -> None:
        activity = self.db.add_activity("  Новая   активность  ")

        self.assertEqual(activity.name, "Новая активность")

    def test_long_name_is_rejected(self) -> None:
        with self.assertRaises(DatabaseError):
            self.db.add_activity("я" * (MAX_ACTIVITY_NAME_LENGTH + 1))

    def test_rename_keeps_default_flag(self) -> None:
        default = next(item for item in self.db.list_activities() if item.is_default)

        renamed = self.db.rename_activity(default.id, "Сплю")

        self.assertEqual(renamed.name, "Сплю")
        self.assertTrue(renamed.is_default)
        self.assertEqual(self.db.get_activity(default.id), renamed)

    def test_rename_to_existing_name_is_rejected(self) -> None:
        first, second = self.db.list_activities()[:2]

        with self.assertRaises(ActivityExistsError):
            self.db.rename_activity(first.id, second.name)

    def test_rename_unknown_activity_is_rejected(self) -> None:
        with self.assertRaises(DatabaseError):
            self.db.rename_activity(9999, "Неизвестно")

    def test_delete_custom_activity(self) -> None:
        activity = self.db.add_activity("Удалить меня")

        self.db.delete_activity(activity.id)

        self.assertIsNone(self.db.get_activity(activity.id))

    def test_delete_default_activity_is_rejected(self) -> None:
        default = next(item for item in self.db.list_activities() if item.is_default)

        with self.assertRaises(DatabaseError):
            self.db.delete_activity(default.id)

        self.assertIsNotNone(self.db.get_activity(default.id))

    def test_delete_activity_with_logs_is_rejected(self) -> None:
        activity = self.db.add_activity("С записями")
        self.db.log_activity(activity.id)

        with self.assertRaises(DatabaseError):
            self.db.delete_activity(activity.id)

        self.assertIsNotNone(self.db.get_activity(activity.id))

    def test_delete_unknown_activity_is_rejected(self) -> None:
        with self.assertRaises(DatabaseError):
            self.db.delete_activity(9999)
