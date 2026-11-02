import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from news import stories, trades


class TradeDirectionTests(unittest.TestCase):
    def setUp(self):
        self.players = {1: "Shane Wright", 2: "Matthew Wood", 3: "Remi Poirier"}
        self.names = {
            "1": {"ru": "Шейн Райт", "surname": "Райт"},
            "2": {"ru": "Мэттью Вуд", "surname": "Вуд"},
            "3": {"ru": "Реми Пуарье", "surname": "Пуарье"},
        }
        self.clubs = {"NSH": "Нэшвилл", "SEA": "Сиэтл", "WSH": "Вашингтон", "NJD": "Нью-Джерси"}

    def facts(self, headline, lead=""):
        return trades.extract(headline, lead, self.players, stories.TEAM_EN)

    def test_wright_headlines_agree_with_club_acquisition(self):
        for headline in (
            "Predators acquire Wright from Kraken for Wood",
            "Kraken trade Wright to Predators for Wood",
            "Shane Wright traded to Nashville Predators by Seattle Kraken for Matthew Wood",
        ):
            with self.subTest(headline=headline):
                facts = self.facts(headline)
                self.assertEqual(facts.moves, (trades.Move(1, "SEA", "NSH"), trades.Move(2, "NSH", "SEA")))
                self.assertEqual(facts.reason, "")

    def test_poirier_primary_release_has_pick_as_unverified_consideration(self):
        facts = self.facts(
            "Capitals Acquire Remi Poirier from New Jersey",
            "The Washington Capitals have acquired goaltender Remi Poirier from the New Jersey Devils "
            "in exchange for a seventh-round pick in the 2027 NHL Draft.",
        )
        self.assertEqual(facts.moves, (trades.Move(3, "NJD", "WSH"),))
        self.assertIn("seventh-round", facts.consideration)
        issues, notes = trades.check(
            "Вашингтон получил Пуарье\n\nКлуб отдал выбор 7-го раунда.", facts, self.names, self.clubs
        )
        self.assertFalse(issues)
        self.assertTrue(notes)

    def test_reversed_receive_and_give_are_blocked(self):
        facts = self.facts("Predators acquire Wright from Kraken for Wood")
        for text in ("Сиэтл получил Райта", "Нэшвилл отдал Райта", "Сиэтл получил Райта. Нэшвилл получил Вуда."):
            with self.subTest(text=text):
                issues, _ = trades.check(text, facts, self.names, self.clubs)
                self.assertTrue(issues)

    def test_poirier_reversed_disposal_is_blocked(self):
        facts = self.facts("Capitals acquire Remi Poirier from New Jersey")
        issues, _ = trades.check("Вашингтон отдал Пуарье", facts, self.names, self.clubs)
        self.assertTrue(issues)

    def test_two_explicit_player_movements_pass(self):
        facts = self.facts("Predators acquire Wright from Kraken for Wood")
        issues, notes = trades.check("Нэшвилл получил Райта\n\nСиэтл получил Вуда.", facts, self.names, self.clubs)
        self.assertEqual((issues, notes), ([], []))

    def test_unverified_wording_and_second_clause_never_auto_pass(self):
        facts = self.facts("Predators acquire Wright from Kraken for Wood")
        for text in (
            "Райт перешёл из Нэшвилла в Сиэтл",
            "Нэшвилл не получил Райта",
            "Нэшвилл получил Райта из Нью-Джерси",
            "Нэшвилл получил Райта, а Вуд достался Нэшвиллу",
            "Нэшвилл получил Райта. Вуд отправился в Нэшвилл.",
            "Нэшвилл получил Райта. Взамен отдал выбор драфта.",
        ):
            with self.subTest(text=text):
                issues, notes = trades.check(text, facts, self.names, self.clubs)
                self.assertTrue(issues or notes)

    def test_uncertain_sources_require_review(self):
        for headline in (
            "Predators acquire Wright",
            "Predators may acquire Wright from Kraken for Wood",
            "Predators will acquire Wright from Kraken for Wood",
            "Predators did not acquire Wright from Kraken for Wood",
            "Predators acquire Wright and a pick from Kraken for Wood",
            "Predators acquire Wright from Kraken via Devils for Wood",
            "Predators acquire Wright from Kraken after Devils trade",
        ):
            with self.subTest(headline=headline):
                facts = self.facts(headline)
                self.assertFalse(facts.moves)
                self.assertTrue(trades.check("Нэшвилл получил Райта", facts, self.names, self.clubs)[1])

    def test_unparsed_lead_cannot_be_overridden_by_confident_headline(self):
        facts = self.facts("Predators acquire Wright from Kraken for Wood",
                           "Wright will remain with the Seattle Kraken.")
        self.assertTrue(facts.reason)
        self.assertTrue(trades.check("Нэшвилл получил Райта. Сиэтл получил Вуда.",
                                     facts, self.names, self.clubs)[1])

    def test_background_trade_is_not_evidence(self):
        facts = self.facts(
            "Wright trade analysis", "Wright scored twice. Predators acquire Wright from Kraken for Wood."
        )
        self.assertFalse(facts.moves)

    def test_conflicting_headline_and_lead_require_review(self):
        facts = self.facts(
            "Predators acquire Wright from Kraken for Wood",
            "Kraken acquire Shane Wright from Predators for Matthew Wood.",
        )
        self.assertFalse(facts.moves)
        self.assertIn("расходятся", facts.reason)

    def test_extra_assets_or_conditions_require_review(self):
        for asset in ("Wood and a seventh-round pick", "Wood with salary retained", "Wood and future considerations"):
            with self.subTest(asset=asset):
                facts = self.facts(f"Predators acquire Wright from Kraken for {asset}")
                self.assertTrue(facts.reason)

    def test_card_uses_transaction_clubs_and_saved_facts_are_serializable(self):
        story = stories.Story(
            "1",
            "trade",
            "Predators acquire Wright from Kraken for Wood",
            "",
            datetime(2026, 11, 2, tzinfo=timezone.utc),
            "trade",
            {1, 2},
            {"NJD", "NSH", "SEA"},
            True,
            text="Shane Wright played New Jersey last week.",
            en=self.players,
        )
        with patch.object(stories, "render_story_card") as render:
            stories.card(
                story,
                "Нэшвилл получил Райта\n\nСиэтл получил Вуда.",
                self.names,
                set(),
                [],
                self.clubs,
                "2026-11-02",
                Path("unused.png"),
            )
            self.assertEqual(render.call_args.args[1], ["SEA", "NSH"])
        import json

        data = json.loads(json.dumps(stories.trade_facts(story).data()))
        self.assertEqual(data["moves"][0], {"pid": 1, "source": "SEA", "destination": "NSH"})
        story.headline = "Wright trade analysis"
        with patch.object(stories, "render_story_card") as render:
            stories.card(
                story,
                "Райт сменил клуб\n\nПодробности обмена.",
                self.names,
                set(),
                [],
                self.clubs,
                "2026-11-02",
                Path("unused.png"),
            )
            self.assertEqual(render.call_args.args[1], [])

    def test_prompt_and_guard_use_same_facts(self):
        story = stories.Story(
            "1",
            "trade",
            "Predators acquire Wright from Kraken for Wood",
            "",
            datetime(2026, 11, 2, tzinfo=timezone.utc),
            "trade",
            {1, 2},
            {"NSH", "SEA"},
            True,
            en=self.players,
        )
        self.assertIn("Нэшвилл получил: Шейн Райт", stories.prompt_for(story, self.names, self.clubs, set()))
        issues, _ = stories.check(
            "Сиэтл получил Райта\n\nНэшвилл получил Вуда.", story, self.names, {}, self.clubs, set()
        )
        self.assertTrue(any("противоречит" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
