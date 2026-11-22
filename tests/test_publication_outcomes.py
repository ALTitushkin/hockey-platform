import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from news import nhl, publish, run, service


class PublicationOutcomeTests(TestCase):
    def test_missing_scoreboard_does_not_mean_no_games(self):
        for read in (nhl.pending_games, nhl.upcoming_games):
            with self.subTest(read=read), patch.object(nhl, "fetch_json", return_value={}):
                with self.assertRaises(RuntimeError):
                    read("2026-11-21")
            with patch.object(nhl, "fetch_json", return_value={"games": []}):
                self.assertFalse(read("2026-11-21"))

    def test_deadline_keeps_empty_unfinished_night_pending(self):
        with patch.object(run, "load", return_value=({"players": {}}, {})), \
                patch.object(nhl, "collect_night", return_value=[]), \
                patch.object(nhl, "pending_games", return_value=1):
            self.assertEqual(run.build_night("2026-11-22", None, False, True), "pending")
            self.assertEqual(run.build_league("2026-11-22", False, True), "pending")

    def test_review_and_confirmed_delivery_are_distinct(self):
        day = "2026-11-22"
        with TemporaryDirectory() as directory, patch.object(publish, "OUT", Path(directory)):
            path = publish.draft_path(day, "night")
            self.assertEqual(service.job_outcome(day, "night", "ok"), "missing_draft")
            path.write_text(json.dumps({"published": []}), encoding="utf-8")
            self.assertEqual(service.job_outcome(day, "night", "ok"), "review")
            path.write_text(json.dumps({"published": ["tg"], "messages": {"tg": [112]}}), encoding="utf-8")
            self.assertEqual(service.job_outcome(day, "night", "ok"), "published")
