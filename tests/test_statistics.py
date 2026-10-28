"""Тесты статистики и настроек интервала таймера."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from database import (
    DEFAULT_INTERVAL_MINUTES,
    INTERVAL_SETTING_KEY,
    MAX_INTERVAL_MINUTES,
    MIN_INTERVAL_MINUTES,
    Database,
    DatabaseError,
)
from tests.db_test_case import TempDatabaseTestCase


class StatisticsTest(TempDatabaseTestCase):
    def test_activity_totals_count_entries_in_period(self) -> None:
        activity = self.db.list_activities()[0]
        self.db.log_activity(activity.id, datetime.now())
        self.db.log_activity(activity.id, datetime.now() - timedelta(days=10))

        stats = {item.activity_id: item.count for item in self.db.activity_totals(7)}

        self.assertEqual(stats[activity.id], 1)

    def test_activity_totals_include_empty_activities(self) -> None:
        stats = self.db.activity_totals(7)

        self.assertEqual(len(stats), len(self.db.list_activities()))
        self.assertTrue(all(item.count == 0 for item in stats))

    def test_activity_totals_are_sorted_by_count(self) -> None:
        first, second = self.db.list_activities()[:2]
        self.db.log_activity(first.id)
        self.db.log_activity(first.id)
        self.db.log_activity(second.id)

        stats = self.db.activity_totals(7)

        self.assertEqual(stats[0].activity_id, first.id)
        self.assertEqual(stats[0].count, 2)
        self.assertEqual(stats[1].activity_id, second.id)
        self.assertEqual(stats[1].count, 1)

    def test_daily_totals_fill_empty_days(self) -> None:
        activity = self.db.list_activities()[0]
        today = date.today()
        self.db.log_activity(activity.id, datetime.now())
        self.db.log_activity(activity.id, datetime.now())
        self.db.log_activity(activity.id, datetime.now() - timedelta(days=1))

        totals = self.db.daily_totals(7)

        self.assertEqual(len(totals), 7)
        self.assertEqual(list(totals), [today - timedelta(days=6 - i) for i in range(7)])
        self.assertEqual(totals[today], 2)
        self.assertEqual(totals[today - timedelta(days=1)], 1)
        self.assertEqual(totals[today - timedelta(days=2)], 0)


class IntervalSettingTest(TempDatabaseTestCase):
    def test_default_interval(self) -> None:
        self.assertEqual(self.db.get_interval_minutes(), DEFAULT_INTERVAL_MINUTES)

    def test_interval_persists(self) -> None:
        self.db.set_interval_minutes(40)

        other = Database(self.db_path)

        self.assertEqual(other.get_interval_minutes(), 40)

    def test_interval_accepts_boundaries(self) -> None:
        self.db.set_interval_minutes(MIN_INTERVAL_MINUTES)
        self.assertEqual(self.db.get_interval_minutes(), MIN_INTERVAL_MINUTES)

        self.db.set_interval_minutes(MAX_INTERVAL_MINUTES)
        self.assertEqual(self.db.get_interval_minutes(), MAX_INTERVAL_MINUTES)

    def test_invalid_interval_is_rejected(self) -> None:
        for value in (0, MAX_INTERVAL_MINUTES + 1, True, "30", 25.5):
            with self.subTest(value=value):
                with self.assertRaises(DatabaseError):
                    self.db.set_interval_minutes(value)

    def test_corrupted_interval_falls_back_to_default(self) -> None:
        self.db.set_setting(INTERVAL_SETTING_KEY, "not-a-number")

        with self.assertLogs("database", level="WARNING"):
            minutes = self.db.get_interval_minutes()

        self.assertEqual(minutes, DEFAULT_INTERVAL_MINUTES)

    def test_interval_is_clamped_when_read(self) -> None:
        self.db.set_setting(INTERVAL_SETTING_KEY, str(MAX_INTERVAL_MINUTES + 1))
        self.assertEqual(self.db.get_interval_minutes(), MAX_INTERVAL_MINUTES)

        self.db.set_setting(INTERVAL_SETTING_KEY, "0")
        self.assertEqual(self.db.get_interval_minutes(), MIN_INTERVAL_MINUTES)
