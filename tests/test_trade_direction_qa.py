"""Adversarial trade direction regressions: all examples are offline/fixed date."""

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from news import publish, stories, trades


class TradeDirectionQATests(unittest.TestCase):
    players = {1: "Shane Wright", 2: "Matthew Wood", 3: "Remi Poirier"}
    names = {
        "1": {"ru": "Шейн Райт", "surname": "Райт"},
        "2": {"ru": "Мэттью Вуд", "surname": "Вуд"},
        "3": {"ru": "Реми Пуарье", "surname": "Пуарье"},
    }
    clubs = {"NSH": "Нэшвилл", "SEA": "Сиэтл", "WSH": "Вашингтон", "NJD": "Нью-Джерси"}

    def facts(self, lead=""):
        return trades.extract("Predators acquire Wright from Kraken for Wood", lead, self.players, stories.TEAM_EN)

    def test_second_direction_clause_with_pronoun_requires_review(self):
        for body in ("Нэшвилл получил Райта и отдал его Сиэтлу", "Нэшвилл получил Райта и затем отдал его Сиэтлу"):
            with self.subTest(body=body):
                issues, notes = trades.check(body, self.facts(), self.names, self.clubs)
                self.assertTrue(issues or notes, "Unverified second transfer must disable automatic publishing")

    def test_conflicting_consideration_between_headline_and_lead_requires_review(self):
        facts = self.facts("Predators acquire Shane Wright from Kraken for Remi Poirier.")
        issues, notes = trades.check("Нэшвилл получил Райта. Сиэтл получил Вуда.", facts, self.names, self.clubs)
        self.assertTrue(issues or notes, "Conflicting consideration must disable automatic publishing")

    def test_additional_pick_in_lead_is_not_hidden_by_short_headline(self):
        facts = self.facts("Predators acquire Shane Wright from Kraken for Matthew Wood and a seventh-round pick.")
        issues, notes = trades.check("Нэшвилл получил Райта. Сиэтл получил Вуда.", facts, self.names, self.clubs)
        self.assertTrue(issues or notes, "A shorter title cannot erase unverified pick compensation in the lead")

    def test_negated_recipient_in_compensation_requires_review(self):
        facts = self.facts()
        issues, notes = trades.check("Нэшвилл получил Райта. Не Сиэтл получил Вуда.", facts, self.names, self.clubs)
        self.assertTrue(issues or notes, "Negated club subject must not count as confirmed receipt")

    def test_implicit_reversed_club_membership_requires_review(self):
        issues, notes = trades.check(
            "Нэшвилл получил Райта. Вуд теперь в Нэшвилле.", self.facts(), self.names, self.clubs
        )
        self.assertTrue(issues or notes)

    def test_process_persists_facts_and_disables_auto_for_unknown_direction(self):
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        story = stories.Story(
            "tradeqa", "tradeqa", "Predators acquire Wright", "", now, "trade", {1, 2}, {"NSH", "SEA"}, True
        )
        body = "Нэшвилл получил Райта\n\nСиэтл получил Вуда."

        def write(prompt, accept):
            prompt(None)
            self.assertFalse(accept(body))
            return body, "offline", []

        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(publish, "OUT", Path(tmp)),
            patch.object(stories, "STATE", Path(tmp) / "state.json"),
            patch.object(stories, "parse_item", return_value=story),
            patch.object(stories, "select", return_value=[story]),
            patch.object(stories, "body_text", return_value=("Source without explicit trade direction.", self.players)),
            patch.object(stories, "card", return_value=Path(tmp) / "card.png"),
        ):
            stories.process(
                now,
                lambda url: {"items": [{}]},
                {},
                self.clubs,
                lambda ids, registry: self.names,
                write,
                lambda: [],
                lambda msk, kind: (True, "offline review"),
                lambda text: None,
            )
            draft = json.loads(publish.draft_path("2026-11-02", "story-tradeqa").read_text(encoding="utf-8"))
            self.assertFalse(draft["data"]["auto"])
            self.assertEqual(draft["data"]["trade_facts"]["moves"], [])
            self.assertTrue(draft["data"]["trade_facts"]["reason"])


if __name__ == "__main__":
    unittest.main()
