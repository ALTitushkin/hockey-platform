"""Offline weekly build/delivery/scheduling contracts."""

import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from news import publish, run, weekly


class WeeklyQATests(unittest.TestCase):
    monday = "2026-11-02"
    players = {"1": {"ru": "Иван Петров", "surname": "Петров", "status": "confirmed"}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.patch(publish, "OUT", self.out)

    def patch(self, obj, name, value):
        patcher = patch.object(obj, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def data(self):
        return {
            "start": "2026-10-26",
            "end": "2026-11-01",
            "sources": ["offline"],
            "skaters": [{"pid": 1, "gamesPlayed": 3, "goals": 2, "assists": 1, "points": 3}],
            "goalies": [],
        }

    def test_real_render_guard_and_save_always_require_owner_review(self):
        with (
            patch.object(run, "load", return_value=({"players": self.players}, {})),
            patch.object(run.nhl, "pending_games", return_value=False) as pending,
            patch.object(weekly, "collect", return_value=self.data()),
            patch.dict(os.environ, {"NEWS_AUTO_PUBLISH": "1"}),
            patch.object(publish, "review", return_value=(True, "offline")) as review,
            patch.object(publish, "auto_publish") as auto,
        ):
            self.assertEqual(run.build_weekly(self.monday, True), "ok")
            pending.assert_called_once_with("2026-11-01")
            review.assert_called_once_with(self.monday, kind="weekly")
            auto.assert_not_called()
        draft = json.loads(publish.draft_path(self.monday, "weekly").read_text(encoding="utf-8"))
        self.assertEqual(draft["issues"], [])
        self.assertFalse(draft["data"]["auto"])
        self.assertEqual(draft["data"]["start"], "2026-10-26")
        self.assertEqual(draft["data"]["end"], "2026-11-01")
        self.assertIn("#НеделяНаших", draft["text"])

    def test_existing_draft_retry_never_fetches_or_rebuilds(self):
        publish.save_draft(self.monday, "saved", [], "offline", kind="weekly", data={"auto": False})
        with (
            patch.object(run, "load", side_effect=AssertionError("no rebuild")),
            patch.object(run.nhl, "pending_games", side_effect=AssertionError("no refetch")),
            patch.object(publish, "review", side_effect=[(False, "offline"), (True, "ok")]),
            patch.object(publish, "auto_publish") as auto,
            patch.dict(os.environ, {"NEWS_AUTO_PUBLISH": "1"}),
        ):
            self.assertEqual(run.build_weekly(self.monday, True), "retry")
            self.assertEqual(run.build_weekly(self.monday, True), "ok")
            auto.assert_not_called()
        draft = json.loads(publish.draft_path(self.monday, "weekly").read_text(encoding="utf-8"))
        self.assertEqual(draft["text"], "saved")

    def test_rejected_weekly_draft_is_not_redelivered_or_rebuilt(self):
        path = publish.save_draft(self.monday, "saved", [], "offline", kind="weekly", data={"auto": False})
        draft = json.loads(path.read_text(encoding="utf-8"))
        draft["rejected"] = True
        path.write_text(json.dumps(draft), encoding="utf-8")
        with (
            patch.object(publish, "review") as review,
            patch.object(publish, "auto_publish") as auto,
            patch.object(run, "load", side_effect=AssertionError("no rebuild")),
        ):
            self.assertEqual(run.build_weekly(self.monday, True), "ok")
            review.assert_not_called()
            auto.assert_not_called()

    def test_already_published_weekly_channel_is_not_sent_twice(self):
        path = publish.save_draft(self.monday, "saved", [], "offline", kind="weekly", data={"auto": False})
        draft = json.loads(path.read_text(encoding="utf-8"))
        draft["published"] = ["tg"]
        path.write_text(json.dumps(draft), encoding="utf-8")
        with patch.object(publish, "tg_send", side_effect=AssertionError("duplicate send")):
            ok, report = publish.publish(self.monday, ["tg"], kind="weekly")
            self.assertTrue(ok, report)

    def test_pending_sunday_blocks_collection_even_after_deadline(self):
        with (
            patch.object(run.nhl, "pending_games", return_value=True),
            patch.object(weekly, "collect", side_effect=AssertionError("partial week")),
        ):
            self.assertEqual(run.build_weekly(self.monday, True, last_try=True), "pending")
            self.assertFalse(publish.draft_path(self.monday, "weekly").exists())

    def test_scheduler_only_calls_weekly_builder_on_monday(self):
        with (
            patch.object(run, "discussion_levels", return_value=None),
            patch.object(run.service, "run_forever") as forever,
            patch.object(run, "build_weekly", return_value="guard") as build,
        ):
            run.cmd_serve(None)
            jobs = forever.call_args.args[0]
            job = next(j for j in jobs if j[0] == "weekly")
            self.assertEqual(job[1:3], ("NEWS_WEEKLY_AT", "12:30"))
            for delta in range(1, 7):
                day = date.fromisoformat(self.monday) + timedelta(days=delta)
                self.assertEqual(job[3](day.isoformat(), True), "nogames")
            build.assert_not_called()
            self.assertEqual(job[3](self.monday, True), "ok")
            build.assert_called_once_with(self.monday, True, True)

    def test_non_monday_is_rejected_before_source_or_delivery(self):
        with patch.object(weekly, "collect") as collect, patch.object(publish, "review") as review:
            with self.assertRaises(ValueError):
                run.build_weekly("2026-11-03", True)
            collect.assert_not_called()
            review.assert_not_called()

    def test_new_year_period_is_exact_previous_seven_days(self):
        self.assertEqual(weekly.period("2027-01-04"), ("2026-12-28", "2027-01-03"))
        self.assertEqual(weekly.period("2024-03-04"), ("2024-02-26", "2024-03-03"))

    def test_cli_build_does_not_erase_existing_owner_rejection(self):
        path = publish.save_draft(self.monday, "rejected text", [], "offline", kind="weekly", data={"auto": False})
        draft = json.loads(path.read_text(encoding="utf-8"))
        draft["rejected"] = True
        path.write_text(json.dumps(draft), encoding="utf-8")
        with (
            patch.object(run, "load", return_value=({"players": self.players}, {})),
            patch.object(run.nhl, "pending_games", return_value=False),
            patch.object(weekly, "collect", return_value=self.data()),
        ):
            run.build_weekly(self.monday, False)
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertTrue(saved.get("rejected"), "Rebuilding a draft must preserve the owner's rejection")


if __name__ == "__main__":
    unittest.main()
