"""Тесты журнала активности и последних записей."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timedelta

from database import DatabaseError
from tests.db_test_case import TempDatabaseTestCase


class ActivityLogTest(TempDatabaseTestCase):
    def test_log_activity_returns_increasing_ids(self) -> None:
        activity = self.db.list_activities()[0]

        first_id = self.db.log_activity(activity.id)
        second_id = self.db.log_activity(activity.id)

        self.assertGreater(second_id, first_id)

    def test_log_unknown_activity_is_rejected(self) -> None:
        with self.assertRaises(DatabaseError):
            self.db.log_activity(9999)

    def test_recent_logs_are_sorted_newest_first(self) -> None:
        activity = self.db.list_activities()[0]
        self.db.log_activity(activity.id, datetime(2026, 10, 1, 10, 0, 0))
        self.db.log_activity(activity.id, datetime(2026, 10, 2, 10, 0, 0))
        self.db.log_activity(activity.id, datetime(2026, 10, 1, 12, 0, 0))

        timestamps = [entry.timestamp for entry in self.db.recent_logs()]

        self.assertEqual(
            timestamps,
            [
                datetime(2026, 10, 2, 10, 0, 0),
                datetime(2026, 10, 1, 12, 0, 0),
                datetime(2026, 10, 1, 10, 0, 0),
            ],
        )

    def test_recent_logs_break_ties_by_id(self) -> None:
        first, second = self.db.list_activities()[:2]
        moment = datetime(2026, 10, 1, 10, 0, 0)
        self.db.log_activity(first.id, moment)
        self.db.log_activity(second.id, moment)

        entries = self.db.recent_logs(2)

        self.assertEqual(
            [entry.activity_id for entry in entries],
            [second.id, first.id],
        )

    def test_recent_logs_respect_limit(self) -> None:
        activity = self.db.list_activities()[0]
        for offset in range(3):
            self.db.log_activity(
                activity.id,
                datetime(2026, 10, 1, 10, 0, 0) + timedelta(minutes=offset),
            )

        self.assertEqual(len(self.db.recent_logs(2)), 2)
        self.assertEqual(len(self.db.recent_logs(0)), 1)

    def test_timestamp_is_normalized(self) -> None:
        activity = self.db.list_activities()[0]
        moment = datetime(2026, 10, 1, 12, 30, 45, 123456)
        log_id = self.db.log_activity(activity.id, moment)

        with closing(sqlite3.connect(self.db_path)) as connection:
            stored = connection.execute(
                "SELECT timestamp FROM logs WHERE id = ?",
                (log_id,),
            ).fetchone()[0]

        self.assertEqual(stored, "2026-10-01 12:30:45")
        self.assertEqual(
            self.db.recent_logs(1)[0].timestamp,
            datetime(2026, 10, 1, 12, 30, 45),
        )

    def test_recent_logs_skip_malformed_timestamp(self) -> None:
        activity = self.db.list_activities()[0]
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute(
                "INSERT INTO logs (activity_id, timestamp) VALUES (?, ?)",
                (activity.id, "not-a-date"),
            )
            connection.commit()

        with self.assertLogs("database", level="WARNING"):
            entries = self.db.recent_logs()

        self.assertEqual(entries, [])
