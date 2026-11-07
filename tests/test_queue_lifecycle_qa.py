"""Offline lifecycle contracts, with an explicit clock for every dated decision."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from news import editorial_lifecycle, editorial_queue, publish


class LifecycleQA(unittest.TestCase):
    def draft(self, **updates):
        value = {"date": "2026-11-07", "text": "Пост", "issues": [], "data": {}}
        value.update(updates)
        return value

    def status(self, draft, kind, at):
        return editorial_lifecycle.classify(draft, kind, datetime.fromisoformat(at))[0]

    def test_daily_expiry_is_moscow_midnight_and_identical_for_manual_or_auto(self):
        for kind in ("night", "league"):
            with self.subTest(kind=kind):
                self.assertNotEqual(self.status(self.draft(), kind, "2026-11-07T20:59:59+00:00"), "expired")
                self.assertEqual(self.status(self.draft(), kind, "2026-11-07T21:00:00+00:00"), "expired")

    def test_weekly_expires_before_next_edition_instead_of_after_one_day(self):
        draft = self.draft(date="2026-11-02")
        self.assertEqual(self.status(draft, "weekly", "2026-11-03T12:00:00+00:00"), "ready")
        self.assertEqual(self.status(draft, "weekly", "2026-11-09T00:00:00+03:00"), "expired")

    def test_announcement_expires_at_first_game_not_last_game(self):
        draft = self.draft(data={"games": [{"start": "2026-11-07T22:00:00Z"},
                                            {"start": "2026-11-08T02:00:00Z"}]})
        self.assertEqual(self.status(draft, "tonight", "2026-11-07T23:00:00+00:00"), "expired")

    def test_announcement_without_proven_start_never_becomes_ready(self):
        self.assertNotEqual(self.status(self.draft(), "tonight", "2026-11-07T12:00:00+00:00"), "ready")

    def test_announcement_explicit_deadline_cannot_extend_past_game_start(self):
        draft = self.draft(data={"expires_at": "2026-11-08T12:00:00+00:00",
                                 "games": [{"start": "2026-11-07T22:00:00Z"}]})
        self.assertEqual(self.status(draft, "tonight", "2026-11-07T23:00:00+00:00"), "expired")
        draft["data"].pop("games")
        self.assertNotEqual(self.status(draft, "tonight", "2026-11-07T12:00:00+00:00"), "ready")

    def test_old_article_without_snapshot_never_becomes_ready(self):
        draft = self.draft(date="2026-10-28", data={"auto": True})
        self.assertEqual(self.status(draft, "story-halloween", "2026-11-07T12:00:00+00:00"), "legacy_review")

    def test_legacy_article_cannot_gain_permission_only_from_future_deadline(self):
        draft = self.draft(data={"expires_at": "2026-12-01T00:00:00+00:00"})
        self.assertEqual(self.status(draft, "story-legacy", "2026-11-07T12:00:00+00:00"), "legacy_review")

    def test_health_without_time_bound_requires_revalidation(self):
        draft = self.draft(data={"source_snapshot": {"content_hash": "source"},
                                 "event_revision": {"family": "health"}})
        self.assertEqual(self.status(draft, "story-health", "2026-11-07T12:00:00+00:00"),
                         "needs_revalidation")

    def test_explicit_return_forecast_expires_without_inventing_new_date(self):
        draft = self.draft(data={"source_snapshot": {"content_hash": "source"},
                                 "event_revision": {"family": "health"},
                                 "expires_at": "2026-11-07T12:00:00+00:00"})
        self.assertEqual(self.status(draft, "story-return", "2026-11-07T12:00:00+00:00"), "expired")

    def test_bad_naive_deadline_does_not_crash_or_grant_ready(self):
        for value in ("wrong", "2026-11-07T14:00:00", 0):
            with self.subTest(value=value):
                draft = self.draft(data={"expires_at": value})
                self.assertNotEqual(self.status(draft, "tonight", "2026-11-07T12:00:00+00:00"), "ready")

    def test_missing_date_is_not_current_date(self):
        draft = self.draft()
        del draft["date"]
        self.assertNotEqual(self.status(draft, "night", "2026-11-07T12:00:00+00:00"), "ready")


class CloseQueueQA(unittest.TestCase):
    def setUp(self):
        clock = patch("news.editorial_lifecycle.utcnow", return_value=datetime(2026, 11, 7, 12, tzinfo=timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name)
        out = patch.object(publish, "OUT", self.out)
        out.start()
        self.addCleanup(out.stop)
        self.path = publish.save_draft("2026-11-07", "legacy", [], "review", kind="story-one")

    def read(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def test_close_preserves_draft_and_reason_through_restart_rebuild(self):
        revision = publish.fingerprint_for_close(self.read())
        publish.close_draft("2026-11-07", "story-one", revision, "Устаревший материал")
        closed = self.read()["editorial_closed"]
        self.assertEqual(publish.editorial_pending(), [])
        publish.save_draft("2026-11-07", "rebuilt", [], "review", kind="story-one")
        self.assertEqual(self.read()["editorial_closed"], closed)
        sender = Mock()
        self.assertFalse(publish.publish("2026-11-07", ["tg"], sender, kind="story-one")[0])
        sender.assert_not_called()

    def test_stale_close_and_short_reason_do_not_modify_json(self):
        first = self.path.read_bytes()
        for revision, reason in (("stale", "Достаточная причина"),
                                 (publish.fingerprint_for_close(self.read()), " ")):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                publish.close_draft("2026-11-07", "story-one", revision, reason)
            self.assertEqual(self.path.read_bytes(), first)

    def test_published_receipt_cannot_be_closed_as_an_unpublished_draft(self):
        draft = self.read()
        draft["published"] = ["tg"]
        draft["messages"] = {"tg": [15]}
        self.path.write_text(json.dumps(draft), encoding="utf-8")
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            publish.close_draft("2026-11-07", "story-one", publish.fingerprint_for_close(draft), "Устарел")
        self.assertEqual(self.path.read_bytes(), before)

    def test_uncertain_delivery_cannot_be_hidden_by_closing_task(self):
        draft = self.read()
        queue = editorial_queue.Queue(self.out / "editorial.sqlite3")
        try:
            revision = queue.sync(self.path.name, draft)
            queue.mark(self.path.name, revision, "delivery_unknown")
        finally:
            queue.close()
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            publish.close_draft("2026-11-07", "story-one", publish.fingerprint_for_close(draft), "Устарел")
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
