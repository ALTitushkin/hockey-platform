"""Offline archive -> weekly links and channel-binding integration."""

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from news import achievements, guard, publish, run, weekly
from news.competition import Scope


class AchievementLinksQA(unittest.TestCase):
    players = {
        "1": {"ru": "Иван Петров", "surname": "Петров", "status": "confirmed"},
        "2": {"ru": "Пётр Иванов", "surname": "Иванов", "status": "confirmed"},
    }
    phrase = "100-й гол в НХЛ"
    channel = "@hockey_tests"

    def setUp(self):
        clock = patch("news.editorial_lifecycle.utcnow", return_value=datetime(2026, 11, 1, 12, tzinfo=timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        patcher = patch.object(publish, "OUT", self.out)
        patcher.start()
        self.addCleanup(patcher.stop)

    def archive(self, kind="night", **updates):
        draft = {
            "date": "2026-11-01",
            "text": f"🏆 Иван Петров — {self.phrase}",
            "published": ["tg"],
            "issues": [],
            "messages": {"tg": [41, 42]},
            "channels": {"tg": self.channel},
            "data": {"nhl_date": "2026-10-31", "achievements": [{"pid": 1, "text": self.phrase}],
                     "scope": Scope("20262027").data()},
        }
        draft.update(updates)
        path = self.out / f"2026-11-01_{kind}.json"
        path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        return path

    def load(self):
        return achievements.load(self.out, "2026-10-26", "2026-11-01", self.players, self.channel)

    def test_publish_binds_channel_and_rebuild_preserves_link_target(self):
        publish.save_draft(
            "2026-11-01",
            f"🏆 Иван Петров — {self.phrase}",
            [],
            "offline",
            data={"nhl_date": "2026-10-31", "achievements": [{"pid": 1, "text": self.phrase}]},
        )
        with (
            patch.dict(os.environ, {"NEWS_CHANNEL": self.channel}),
            patch.object(publish, "tg_send", return_value=(True, "message_id 41 42")),
        ):
            self.assertTrue(publish.publish("2026-11-01", ["tg"])[0])
        path = publish.draft_path("2026-11-01")
        original = json.loads(path.read_text(encoding="utf-8"))
        publish.save_draft("2026-11-01", original["text"], [], "rebuilt", data=original["data"])
        rebuilt = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["channels"], {"tg": self.channel})
        self.assertEqual(rebuilt["messages"], {"tg": [41, 42]})
        self.assertEqual(self.load()[0]["url"], "https://t.me/hockey_tests/42")

    def test_deleted_rejected_wrong_channel_or_wrong_player_fail_closed(self):
        variants = [
            {"deleted_messages": {"tg": [42]}},
            {"rejected": True},
            {"channels": {"tg": "@other_channel"}},
            {"published": []},
            {"data": {"nhl_date": "2026-10-30", "achievements": [{"pid": 1, "text": self.phrase}]}},
            {
                "data": {"nhl_date": "2026-10-31", "achievements": [{"pid": 2, "text": self.phrase}]},
                "text": f"🏆 Иван Петров — {self.phrase}\nПётр Иванов сыграл матч.",
            },
        ]
        for variant in variants:
            with self.subTest(variant=variant):
                self.archive(**variant)
                self.assertEqual(self.load(), [])

    def test_night_and_league_same_milestone_link_only_once(self):
        self.archive("night")
        self.archive("league", messages={"tg": [99]})
        found = self.load()
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0]["kind"], found[0]["message_id"]), ("night", 42))

    def test_href_digits_are_not_statistics_but_visible_digits_still_checked(self):
        facts = {"numbers": {"100"}, "pids": {1}, "teams": set()}
        text = f'Иван Петров — <a href="https://t.me/c/123456789/987654">{self.phrase}</a>'
        self.assertEqual(guard.check(text, facts, self.players, {}, publish=True), [])
        issues = guard.check(text.replace(self.phrase, "999-й гол в НХЛ"), facts, self.players, {})
        self.assertTrue(any("999" in issue for issue in issues))

    def test_weekly_build_loads_archive_embeds_link_and_persists_provenance(self):
        self.archive()
        data = {
            "start": "2026-10-26",
            "end": "2026-11-01",
            "sources": [],
            "goalies": [],
            "skaters": [{"pid": 1, "gamesPlayed": 3, "goals": 2, "assists": 1, "points": 3}],
        }
        with (
            patch.dict(os.environ, {"NEWS_CHANNEL": self.channel}),
            patch.object(run, "load", return_value=({"players": self.players}, {})),
            patch.object(run.nhl, "pending_games", return_value=False),
            patch.object(weekly, "collect", return_value=data),
        ):
            self.assertEqual(run.build_weekly("2026-11-02", False), "ok")
        draft = json.loads(publish.draft_path("2026-11-02", "weekly").read_text(encoding="utf-8"))
        self.assertIn(f'<a href="https://t.me/hockey_tests/42">{self.phrase}</a>', draft["text"])
        self.assertEqual(draft["data"]["achievements"][0]["message_id"], 42)
        self.assertFalse(draft["data"]["auto"])

    def test_nightly_builds_persist_only_visible_highlights(self):
        event = SimpleNamespace(pid=1, text=self.phrase)
        hidden = SimpleNamespace(pid=1, text="первый гол в НХЛ")
        final = f"🏆 Иван Петров — {self.phrase}"
        facts = {"numbers": {"100"}, "pids": {1}, "teams": set()}
        reports = [SimpleNamespace(game_id=123, home="NYI", away="MIN", home_score=1, away_score=0,
                                   last_period="REG", skaters=[SimpleNamespace(pid=1)], goalies=[],
                                   scope=Scope("20262027").data())]
        for kind in ("night", "league"):
            with (
                self.subTest(kind=kind),
                patch.object(run, "load", return_value=({"players": self.players}, {})),
                patch.object(run.nhl, "collect_night", return_value=reports),
                patch.object(run.nhl, "fetch_json", return_value={"summary": {"scoring": []}}),
                patch.object(run.events, "context", return_value={}),
                patch.object(run.events, "detect", return_value=[event, hidden]),
                patch.object(run.events, "headline", return_value=[(1, [event, hidden])]),
                patch.object(run.names, "league_players", return_value=self.players),
                patch.object(run, "render_night", return_value=(final, facts)),
                patch.object(run, "render_caption", return_value=(final, facts)),
                patch.object(run, "render_league", return_value=(final, facts)),
                patch.object(run, "render_card", return_value=self.out / "card.png"),
            ):
                result = (
                    run.build_night("2026-11-01", None, False)
                    if kind == "night"
                    else run.build_league("2026-11-01", False)
                )
                self.assertEqual(result, "ok")
                draft = json.loads(publish.draft_path("2026-11-01", kind).read_text(encoding="utf-8"))
                self.assertEqual(
                    draft["data"], {"nhl_date": "2026-10-31", "achievements": [{"pid": 1, "text": self.phrase}],
                                    "scope": Scope("20262027").data()}
                )

    def test_rebuild_does_not_revive_deleted_link(self):
        path = self.archive(deleted_messages={"tg": [42]})
        old = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(self.load(), [])
        publish.save_draft("2026-11-01", old["text"], [], "rebuilt", data=old["data"])
        self.assertEqual(self.load(), [], "Rebuild must retain deletion audit to avoid linking a deleted message")

    def test_malformed_channel_and_deletion_audit_are_skipped(self):
        for variant in (
            {"channels": {"tg": 123}},
            {"deleted_messages": {"tg": None}},
            {"deleted_messages": {"tg": 42}},
        ):
            with self.subTest(variant=variant):
                self.archive(**variant)
                self.assertEqual(self.load(), [], "Malformed adjacent archive file must not break weekly build")


if __name__ == "__main__":
    unittest.main()
