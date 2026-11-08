"""Offline contracts: restart, stale approval, separate competition scopes and auto policy."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from news import content_plan, editorial_queue, events, nhl, publish, weekly
from news.competition import Scope, from_data


class ScopeContracts(unittest.TestCase):
    def test_playoff_first_goal_is_labelled_in_its_own_scope(self):
        report = nhl.GameReport(1, "TOR", "MIN", 1, 0, "REG",
                                skaters=[nhl.SkaterLine(12, "TOR", 1, 0, 1, 2)])
        ctx = {"players": {12: {"this_game": True, "scope_confirmed": True,
                                "scope": Scope("20262027", "playoffs").data(),
                                "career": {"goals": 1, "assists": 0, "points": 1, "games": 1}}}}
        result = events.detect([report], ctx)
        self.assertIn("первый гол в плей-офф НХЛ", [e.text for e in result])
        self.assertNotIn("первый гол в НХЛ", [e.text for e in result])

    def test_no_career_totals_means_no_invented_first_goal(self):
        report = nhl.GameReport(1, "TOR", "MIN", 1, 0, "REG",
                                skaters=[nhl.SkaterLine(12, "TOR", 1, 0, 1, 2)])
        result = events.detect([report], {})
        self.assertNotIn("первый гол в НХЛ", [e.text for e in result])

    def test_unknown_context_never_falls_back_to_regular(self):
        for args in (("20262027", "unknown"), ("20262027", "regular", "world-cup"),
                     ("20262029",), ('20262027 or 1=1',)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                Scope(*args)
        with self.assertRaises(ValueError):
            from_data({**Scope("20262027").data(), "ruleset_version": 42})

    def test_weekly_profiles_share_collector_and_separate_statistics(self):
        for phase, game_type in (("regular", 2), ("playoffs", 3), ("preseason", 1)):
            calls = []
            def fetch(url):
                calls.append(url)
                return {"total": 0, "data": []}
            scope = Scope("20262027", phase)
            data = weekly.collect("2027-05-10", {}, fetch, scope)
            self.assertEqual(data["scope"], scope.data())
            from urllib.parse import unquote
            self.assertTrue(all(f"gameTypeId={game_type}" in unquote(url) for url in calls))

    def test_lineup_does_not_use_regular_game_during_playoffs(self):
        games = [{"id": n, "gameType": t, "gameState": "OFF", "gameDate": "2027-05-01"}
                 for n, t in ((1, 2), (2, 3))]
        box = {"homeTeam": {"abbrev": "TOR"}, "playerByGameStats": {
            "homeTeam": {"forwards": [{"playerId": 12}]}}}
        def fetch(url):
            if "club-schedule" in url:
                return {"games": games}
            self.assertIn("/2/boxscore", url)
            return box
        with patch.object(nhl, "fetch_json", side_effect=fetch):
            self.assertEqual(nhl.last_lineup("TOR", "20262027", "2027-05-02",
                                             Scope("20262027", "playoffs")), {12})


class QueueContracts(unittest.TestCase):
    def setUp(self):
        clock = patch("news.editorial_lifecycle.utcnow", return_value=datetime(2026, 11, 7, 12, tzinfo=timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.patch = patch.object(publish, "OUT", self.out)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def draft(self):
        return publish.save_draft("2026-11-07", "Текст", [], "review", data={"auto": False})

    def test_review_remains_visible_after_restart_and_empty_feed(self):
        path = self.draft()
        self.assertEqual(publish.editorial_pending()[0]["status"], "needs_review")
        self.assertTrue(path.exists())
        self.assertEqual(publish.editorial_pending()[0]["name"], path.name)

    def test_auto_cannot_bypass_review_via_publish(self):
        self.draft()
        calls = []
        ok, why = publish.publish("2026-11-07", ["tg"], lambda *a, **k: calls.append(a), automatic=True)
        self.assertFalse(ok)
        self.assertIn("needs_review", why[0])
        self.assertEqual(calls, [])

    def test_old_approval_cannot_send_or_reject_changed_text(self):
        path = self.draft()
        old = editorial_queue.fingerprint(json.loads(path.read_text(encoding="utf-8")))[:16]
        publish.save_draft("2026-11-07", "Другой текст", [], "review", data={"auto": False})
        calls = []
        ok, _ = publish.publish("2026-11-07", ["tg"], lambda *a, **k: calls.append(a), expected=old)
        self.assertFalse(ok)
        with self.assertRaises(ValueError):
            publish.reject("2026-11-07", expected=old)
        self.assertEqual(calls, [])

    def test_image_change_invalidates_approval(self):
        image = self.out / "card.png"
        image.write_bytes(b"first")
        d = {"text": "x", "card": str(image)}
        before = editorial_queue.fingerprint(d)
        image.write_bytes(b"second")
        self.assertNotEqual(before, editorial_queue.fingerprint(d))

    def test_bad_expiry_is_blocked_not_ignored(self):
        for expiry in ("garbage", "2020-01-01T00:00:00", "2020-01-01T00:00:00+00:00"):
            with self.subTest(expiry=expiry):
                state, _ = editorial_queue.decision({"data": {"expires_at": expiry}})
                self.assertIn(state, ("blocked", "expired"))

    def test_changed_source_supersedes_unpublished_review_and_blocks_its_button(self):
        first = {"auto": False, "source_snapshot": {"url": "source", "content_hash": "first",
                                                   "fetched_at": "2026-11-06T00:00:00+00:00"}}
        publish.save_draft("2026-11-06", "old", [], "review", kind="story-old", data=first)
        newer = {**first, "source_snapshot": {**first["source_snapshot"], "content_hash": "second",
                                              "fetched_at": "2026-11-07T00:00:00+00:00"}}
        publish.save_draft("2026-11-07", "new", [], "review", kind="story-new", data=newer)
        tasks = publish.editorial_pending()
        self.assertEqual([t["name"] for t in tasks], ["2026-11-07_story-new.json"])
        calls = []
        ok, _ = publish.publish("2026-11-06", ["tg"], lambda *a, **k: calls.append(a), kind="story-old")
        self.assertFalse(ok)
        self.assertEqual(calls, [])


class ContentPlan(unittest.TestCase):
    def test_second_recap_chooses_another_angle_and_keeps_all_events(self):
        highlights = [(1, [events.Event(1, 70, "4 очка за матч")]),
                      (2, [events.Event(2, 50, "победный гол")])]
        players = {"1": {"surname": "Первый"}, "2": {"surname": "Второй"}}
        chosen, rubric = content_plan.choose(highlights, players, "Первый — 4 очка за матч")
        self.assertEqual(chosen[0][0], 2)
        self.assertEqual({pid for pid, _ in chosen}, {1, 2})
        self.assertFalse(rubric)

    def test_only_repeated_event_uses_honest_rubric_headline(self):
        highlights = [(1, [events.Event(1, 70, "4 очка за матч")])]
        chosen, rubric = content_plan.choose(highlights, {"1": {"surname": "Первый"}},
                                             "Первый — 4 очка за матч")
        self.assertTrue(rubric)
        self.assertEqual(chosen, highlights)


if __name__ == "__main__":
    unittest.main()
