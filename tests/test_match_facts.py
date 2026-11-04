import unittest
from datetime import datetime, timezone

from news import match_facts, stories
from news.nhl import GameReport, GoalieLine


class MatchFactsTests(unittest.TestCase):
    def test_tarasov_is_bound_to_detroit_even_against_florida(self):
        game = GameReport(2026020233, "FLA", "DET", 3, 5, "REG",
                          goalies=[GoalieLine(1, "DET", 23, 26, "W")])
        text = match_facts.night_lead([game], {"1": {"surname": "Тарасов"}},
                                      {"FLA": "Флорида", "DET": "Детройт"})
        self.assertEqual(text, "Тарасов отразил 23 из 26 бросков. Детройт — Флорида 5:3.")

    def test_contradictory_goalie_decision_cannot_make_a_winner(self):
        game = GameReport(1, "FLA", "DET", 5, 3, "REG", goalies=[GoalieLine(1, "DET", 23, 26, "W")])
        self.assertIsNone(match_facts.night_lead([game], {"1": {"surname": "Тарасов"}}, {}))

    def test_winnipeg_actual_four_goal_comeback(self):
        game = GameReport(2026020237, "MTL", "WPG", 4, 5, "OT")
        scores = [(1, 0), (2, 0), (3, 0), (4, 0), (4, 1), (4, 2), (4, 3), (4, 4), (4, 5)]
        timeline = [{"goals": [{"homeScore": h, "awayScore": a} for h, a in scores]}]
        event = match_facts.comeback(game, timeline)
        self.assertEqual(event["from"], (0, 4))
        self.assertEqual(event["winner"], "WPG")
        self.assertEqual(match_facts.comeback_text(event, {"WPG": "Виннипег", "MTL": "Монреаль"}),
                         "Виннипег отыгрался с 0:4. Виннипег — Монреаль 5:4 ОТ.")

    def test_missing_reordered_and_duplicate_goals_fail_closed(self):
        game = GameReport(1, "MTL", "WPG", 3, 4, "OT")
        for values in ([], [(3, 0), (3, 4)], [(1, 0), (1, 0)], [(1, 0), (0, 0)], [(True, 0)]):
            with self.subTest(values=values):
                timeline = [{"goals": [{"homeScore": h, "awayScore": a} for h, a in values]}]
                self.assertIsNone(match_facts.comeback(game, timeline))

    def test_shootout_and_small_deficit_are_not_large_comebacks(self):
        timeline = [{"goals": [{"homeScore": 1, "awayScore": 0},
                                {"homeScore": 1, "awayScore": 1}, {"homeScore": 1, "awayScore": 2}]}]
        self.assertIsNone(match_facts.comeback(GameReport(1, "MTL", "WPG", 1, 2, "OT"), timeline))
        self.assertIsNone(match_facts.comeback(GameReport(1, "MTL", "WPG", 1, 2, "SO"), timeline))

    def test_malformed_optional_timeline_does_not_break_the_digest(self):
        game = GameReport(1, "MTL", "WPG", 4, 5, "OT")
        for scoring in (None, {}, [None], [{"goals": None}], [{"goals": [None]}]):
            with self.subTest(scoring=scoring):
                self.assertIsNone(match_facts.comeback(game, scoring))

    def test_known_injury_region_cannot_be_replaced_with_vague_injury(self):
        source = stories.Story("injury", "injury", "Forward leaves with upper-body injury", "",
                               datetime(2026, 11, 3, tzinfo=timezone.utc), "injury", set(), set(), True)
        issues, _ = stories.check("Игрок не смог продолжить матч\n\nОн получил травму.", source, {}, {}, {}, set())
        self.assertTrue(any("уточнение травмы" in i for i in issues))
        issues, _ = stories.check("Игрок не смог продолжить матч\n\nУ него травма верхней части тела.",
                                  source, {}, {}, {}, set())
        self.assertFalse(any("уточнение травмы" in i for i in issues))
        source.headline = "Forward leaves game"
        self.assertEqual(stories.health_facts(source), {})
        source.headline = "Forward out with lower-body injury"
        issues, _ = stories.check("Игрок выбыл\n\nУ него травма верхней части тела.",
                                  source, {}, {}, {}, set())
        self.assertTrue(any("уточнение травмы" in i for i in issues))
        issues, _ = stories.check("Игрок выбыл\n\nУ него травма нижней части тела.",
                                  source, {}, {}, {}, set())
        self.assertFalse(any("уточнение травмы" in i for i in issues))
        source.headline = "NHL Status Report: Forward out with lower-body injury"
        self.assertEqual(stories.health_facts(source), {})


if __name__ == "__main__":
    unittest.main()
