"""Offline regression checks for publication provenance and player/team focus."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from news import publish, run, stories, story_provenance
from news.nhl import GameReport


class EditorialSystemQA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
        self.source = stories.Story("followup", "hutton-followup", "Hutton looking to maximize opportunity", "",
                                    self.now, "signing", {1}, {"NYI"}, True,
                                    text="Hutton [signed a PTO](https://www.nhl.com/islanders/news/islanders-sign-hutton).")

    def receipt(self, **changes):
        value = {"date": "2026-11-03", "published": ["tg"], "messages": {"tg": [50]},
                 "data": {"slug": "islanders-sign-hutton"}}
        value.update(changes)
        (self.out / "2026-11-03_story-first.json").write_text(json.dumps(value), encoding="utf-8")

    def test_hutton_receipt_survives_first_article_leaving_current_feed(self):
        self.receipt()
        result = story_provenance.published_reference(self.source, self.out, "2026-11-04")
        self.assertEqual(result, {"slug": "islanders-sign-hutton", "messages": [50]})

    def test_unpublished_rejected_or_deleted_receipts_are_not_evidence(self):
        for changes in ({"published": []}, {"rejected": True}, {"deleted_messages": {"tg": [50]}},
                        {"messages": {"tg": []}}):
            with self.subTest(changes=changes):
                self.receipt(**changes)
                self.assertIsNone(story_provenance.published_reference(self.source, self.out, "2026-11-04"))

    def test_hutton_followup_is_saved_for_review_not_auto_published(self):
        self.receipt()
        body = "Бен Хаттон подписал пробный контракт с Айлендерс\n\nЗащитник провёл тренировку."
        def write(prompt, accept):
            self.assertFalse(accept(body))
            return body, "offline", []
        with (
            patch.object(publish, "OUT", self.out),
            patch.object(stories, "STATE", self.out / "state.json"),
            patch.object(stories, "parse_item", return_value=self.source),
            patch.object(stories, "select", return_value=[self.source]),
            patch.object(stories, "body_text", return_value=(self.source.text, {1: "Ben Hutton"})),
            patch.object(stories, "check", return_value=([], [])),
            patch.object(stories, "goalie_stats", return_value=[]),
            patch.object(stories, "card", return_value=self.out / "unused.png"),
        ):
            stories.process(self.now, lambda url: {"items": [{}]}, {}, {"NYI": "Айлендерс"},
                            lambda pids, reg: {"1": {"ru": "Бен Хаттон", "surname": "Хаттон"}},
                            write, lambda: [], Mock(return_value=(True, "reviewed")), lambda msg: None)
            draft = json.loads(publish.draft_path("2026-11-04", "story-followup").read_text(encoding="utf-8"))
            self.assertFalse(draft["data"]["auto"])
            self.assertIn("islanders-sign-hutton", draft["variant"])
            self.assertEqual(draft["data"]["source_event"]["pids"], [1])

    def test_malformed_receipt_does_not_disable_all_story_processing(self):
        for changes in ({"messages": None}, {"data": None}, {"published": None}):
            with self.subTest(changes=changes):
                self.receipt(**changes)
                self.assertIsNone(story_provenance.published_reference(self.source, self.out, "2026-11-04"))

    def test_receipt_reference_is_exact_article_not_slug_prefix(self):
        self.receipt()
        self.source.text = "[A different article](https://www.nhl.com/news/islanders-sign-hutton-followup)."
        self.assertIsNone(story_provenance.published_reference(self.source, self.out, "2026-11-04"))

    def report(self, text, english=None):
        source = stories.Story("report", "report", "NHL Status Report", "", self.now, "injury", {1},
                               {"MIN", "NYI"}, True, text=text, en=english or {})
        names = {"1": {"ru": "Райан Пулок", "surname": "Пулок"}}
        body = "Райан Пулок выбыл на 2–4 недели\n\nЗащитник Айлендерс травмирован в матче с Миннесотой."
        with patch.object(stories, "render_story_card", return_value=self.out / "none.png") as renderer:
            stories.card(source, body, names, set(), [], {"MIN": "Миннесота", "NYI": "Айлендерс"},
                         "2026-11-04", self.out / "none.png")
            return renderer.call_args.args[1]

    def test_pulock_missing_identity_has_neutral_card_not_alphabetical_opponent(self):
        self.assertEqual(self.report("Ryan Pulock was injured against Minnesota Wild."), [])

    def test_pulock_three_level_heading_binds_islanders_not_opponent(self):
        text = "### **New York Islanders**\nRyan Pulock injured against Minnesota Wild."
        self.assertEqual(self.report(text, {1: "Ryan Pulock"}), ["NYI"])

    def test_multiple_sections_mentioning_player_are_not_unique_ownership(self):
        text = ("## Minnesota Wild\nRyan Pulock was on the opposing team.\n\n"
                "## New York Islanders\nRyan Pulock will miss two weeks.")
        self.assertEqual(self.report(text, {1: "Ryan Pulock"}), [])

    def test_winnipeg_comeback_survives_optional_career_context_failure(self):
        game = GameReport(2026020237, "MTL", "WPG", 4, 5, "OT")
        scores = [(1, 0), (2, 0), (3, 0), (4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (4, 5)]
        scoring = [{"goals": [{"homeScore": h, "awayScore": a} for h, a in scores]}]
        with (
            patch.object(publish, "OUT", self.out),
            patch.object(run, "load", return_value=({"players": {}}, {"MTL": "Монреаль", "WPG": "Виннипег"})),
            patch.object(run.nhl, "collect_night", return_value=[game]),
            patch.object(run.nhl, "fetch_json", return_value={"summary": {"scoring": scoring}}),
            patch.object(run.names, "league_players", return_value={}),
            patch.object(run.events, "context", side_effect=RuntimeError("career API unavailable")),
            patch.object(run, "render_card", return_value=self.out / "none.png"),
        ):
            self.assertEqual(run.build_league("2026-11-04", False), "ok")
            draft = json.loads(publish.draft_path("2026-11-04", "league").read_text(encoding="utf-8"))
            self.assertIn("Виннипег отыгрался с 0:4", draft["text"])
            self.assertIn("5:4 ОТ", draft["text"])
            self.assertEqual(draft["issues"], [])


if __name__ == "__main__":
    unittest.main()
