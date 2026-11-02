import json
import tempfile
import unittest
from pathlib import Path

from news import achievements, events, guard, weekly


class AchievementTests(unittest.TestCase):
    players = {"1": {"ru": "Кирилл Капризов", "surname": "Капризов", "status": "confirmed"},
               "2": {"ru": "Пётр Кочетков", "surname": "Кочетков", "status": "confirmed"}}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)

    def save(self, day="2026-11-02", kind="night", **changes):
        draft = {"date": day, "text": "🎯 <b>Капризов — 500-е очко в НХЛ</b>\n\n🧱 Кочетков — сухой матч",
                 "published": ["tg"], "messages": {"tg": [41]}, "issues": []}
        draft.update(changes)
        (self.out / f"{day}_{kind}.json").write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
        return draft

    def load(self, channel="@hockey_culture"):
        return achievements.load(self.out, "2026-10-26", "2026-11-01", self.players, channel)

    def test_inline_links_and_numeric_guard_apply_to_visible_claims(self):
        self.save()
        found = self.load()
        self.assertEqual([(e["pid"], e["url"]) for e in found],
                         [(1, "https://t.me/hockey_culture/41"), (2, "https://t.me/hockey_culture/41")])
        text, facts = weekly.render({"start": "2026-10-26", "end": "2026-11-01", "skaters": [],
                                     "goalies": [], "achievements": found}, self.players)
        # No appearances: render is intentionally suppressed rather than inventing weekly stats.
        self.assertEqual(text, "")
        data = {"start": "2026-10-26", "end": "2026-11-01", "goalies": [], "achievements": found,
                "skaters": [{"pid": 1, "gamesPlayed": 3, "points": 4, "goals": 2, "assists": 2}]}
        text, facts = weekly.render(data, self.players)
        self.assertIn('<a href="https://t.me/hockey_culture/41">500-е очко в НХЛ</a>', text)
        self.assertIn("🏆 <b>Достижения недели</b>\n", text)
        self.assertNotIn("Подробнее", text)
        self.assertEqual(guard.check(text, facts, self.players, {}), [])
        self.assertTrue(guard.check(text.replace("500-е", "999-е"), facts, self.players, {}))
        self.assertNotIn("41", {str(n) for n in facts["numbers"]})

    def test_nhl_sunday_is_included_through_monday_post(self):
        self.save()
        self.save("2026-10-26", messages={"tg": [1]})
        self.save("2026-11-03", messages={"tg": [55]})
        self.assertEqual({e["message_id"] for e in self.load()}, {41})

    def test_unpublished_rejected_deleted_bad_guard_or_channel_are_excluded(self):
        for changes in ({"published": []}, {"rejected": True}, {"issues": ["ошибка"]},
                        {"deleted_messages": {"tg": [41]}}, {"messages": {"tg": [True]}},
                        {"messages": {"tg": []}}, {"channels": {"tg": "@other_channel"}},
                        {"data": {"nhl_date": "2026-11-02"}}):
            with self.subTest(changes=changes):
                self.save(**changes)
                self.assertEqual(self.load(), [])

    def test_structured_league_and_night_deduplicate_preferring_night(self):
        data = {"nhl_date": "2026-11-01", "achievements": [{"pid": 1, "text": "500-е очко в НХЛ"}]}
        self.save(kind="league", data=data, messages={"tg": [40]})
        self.save(data=data)
        found = self.load()
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["message_id"], 41)
        self.save("2026-10-30", data={**data, "nhl_date": "2026-10-29"}, messages={"tg": [29]})
        self.assertEqual(len(self.load()), 1)

    def test_old_league_cannot_guess_our_player_from_a_surname(self):
        self.save(kind="league")
        self.assertEqual(self.load(), [])

    def test_story_tonight_and_narrative_mentions_are_not_milestones(self):
        self.save(kind="story-trade")
        self.save(kind="tonight")
        self.save(text="Капризову осталось 1 очко до 500.\nКочетков близок к сухому матчу.")
        self.assertEqual(self.load(), [])

    def test_unknown_and_ambiguous_names_do_not_produce_links(self):
        self.save(text="🎯 Неизвестный — 500-е очко в НХЛ")
        self.assertEqual(self.load(), [])
        players = {**self.players, "3": {"ru": "Другой Капризов", "surname": "Капризов"}}
        self.save()
        found = achievements.load(self.out, "2026-10-26", "2026-11-01", players, "@hockey_culture")
        self.assertEqual([e["pid"] for e in found], [2])

    def test_structured_record_must_match_player_event_line_not_separate_mentions(self):
        self.save(data={"achievements": [{"pid": 1, "text": "сухой матч"}]})
        self.assertEqual(self.load(), [])

    def test_split_post_links_to_text_and_ignores_deleted_text(self):
        self.save(messages={"tg": [40, 41]}, deleted_messages={"tg": [40]})
        self.assertEqual({e["message_id"] for e in self.load()}, {41})
        self.save(messages={"tg": [40, 41]}, deleted_messages={"tg": [41]})
        self.assertEqual(self.load(), [])

    def test_safe_public_and_private_links_only(self):
        self.assertEqual(achievements.permalink("-1001234567890", 7), "https://t.me/c/1234567890/7")
        for channel in ("https://evil.test/", '@channel" onclick="x', "@ab", "", "-1234567890"):
            self.assertIsNone(achievements.permalink(channel, 7))
        for mid in (0, -1, True, "7"):
            self.assertIsNone(achievements.permalink("@hockey_culture", mid))

    def test_snapshot_only_includes_known_events_present_in_caption(self):
        high = [(1, [events.Event(1, 85, "500-е очко в НХЛ", {500}), events.Event(1, 100, "1000-е очко в НХЛ")]),
                (2, [events.Event(2, 40, "победный гол")])]
        data = achievements.snapshot(high, "🎯 Капризов — 500-е очко в НХЛ", "2026-11-01")
        self.assertEqual(data, {"nhl_date": "2026-11-01", "achievements": [{"pid": 1, "text": "500-е очко в НХЛ"}]})

    def test_malformed_and_oversized_files_do_not_stop_optional_block(self):
        path = self.out / "2026-11-02_night.json"
        for value in ("bad json", "null", "[]", '{"date":"2026-11-02","published":["tg"],"messages":null}'):
            with self.subTest(value=value):
                path.write_text(value, encoding="utf-8")
                self.assertEqual(self.load(), [])
        path.write_text(" " * (129 * 1024), encoding="utf-8")
        self.assertEqual(self.load(), [])


if __name__ == "__main__":
    unittest.main()
