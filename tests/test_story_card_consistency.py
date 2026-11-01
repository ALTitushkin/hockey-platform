"""Пост №37: карточка Status Report должна соответствовать выбранному пересказу."""
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from news import stories


class StoryCardTests(unittest.TestCase):
    def setUp(self):
        self.story = stories.Story(
            "status-report", "nhl-status-report", "NHL Status Report: Konecny could return for Flyers",
            "", datetime(2026, 11, 1, tzinfo=timezone.utc), "return", {1}, {"PHI"}, True,
            text="Travis Konecny could return for Philadelphia Flyers. Andre Burakovsky of Ottawa Senators is injured.",
            mentioned={1, 2}, en={1: "Travis Konecny", 2: "Andre Burakovsky"})
        self.names = {"1": {"ru": "Трэвис Конекны", "surname": "Конекны"},
                      "2": {"ru": "Андре Бураковски", "surname": "Бураковски"}}
        self.teams = {"PHI": "Филадельфия", "OTT": "Оттава"}
        self.body = "Бураковски пропустит матч Оттавы\n\nНападающий травмирован."

    def render_card(self, body):
        with patch.object(stories, "render_story_card", return_value=Path("card.png")) as render:
            stories.card(self.story, body, self.names, set(), [], self.teams, "2026-11-01", Path("card.png"))
            return render.call_args.args

    def test_post37_card_hero_and_club_follow_rewritten_story(self):
        args = self.render_card(self.body)
        self.assertEqual(args[:3], ("СВОДКА НХЛ", ["OTT"], "Андре Бураковски"))
        self.assertEqual(args[4], self.body.partition("\n\n")[0])

    def test_post37_headline_without_player_does_not_borrow_source_hero(self):
        args = self.render_card("Новости травм\n\nБураковски пропустит матч Оттавы.")
        self.assertIsNone(args[2])
        self.assertNotIn("PHI", args[1])

    def test_post37_status_report_uses_neutral_rubric(self):
        rendered = stories.render(self.story, self.body, "2026-11-01")
        self.assertTrue(rendered.startswith("📰 <b>Бураковски"))
        self.assertIn("#СводкаНХЛ", rendered)
        self.assertNotIn("#Возвращения", rendered)


if __name__ == "__main__":
    unittest.main()
