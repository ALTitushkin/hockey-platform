"""Synthetic regression corpus derived from the editorial failure classes, no network/model."""

import copy
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from news import event_registry, fact_packet


class FactPackets(unittest.TestCase):
    def source(self, **changes):
        data = dict(eid="test", kind="return", link="https://www.nhl.com/news/test", headline="Forward expected back",
                    date=datetime(2026, 11, 6, 20, tzinfo=timezone.utc), pids={1}, teams={"TOR"},
                    en={1: "Test Forward"}, text=("Test Forward is expected to rejoin the Toronto Maple Leafs "
                    "on Saturday. Forward on Friday completed his first full practice in a regular jersey."))
        data.update(changes)
        return SimpleNamespace(**data)

    def extract(self, source):
        return fact_packet.extract(source, {"1": {"ru": "Тестовый Игрок"}},
                                   {"TOR": "Торонто"}, {"TOR": ("Toronto", "Maple Leafs")})

    def test_expected_return_is_not_completed_return_or_contact_practice(self):
        s = self.source()
        p = self.extract(s)
        self.assertIsNotNone(p)
        body = fact_packet.render(p)
        self.assertIn("может вернуться", body)
        self.assertIn("7 ноября", body)
        self.assertIn("6 ноября", body)
        self.assertNotIn("контакт", body)
        self.assertNotIn("большинство", body)
        self.assertEqual(fact_packet.verify(p, fact_packet.snapshot(s), body), [])
        self.assertTrue(event_registry.complete(fact_packet.revision(p)))

    def test_mutated_text_or_source_does_not_get_auto_approval(self):
        s = self.source()
        p = self.extract(s)
        self.assertTrue(fact_packet.verify(p, fact_packet.snapshot(s), "Игрок уже вернулся"))
        source = fact_packet.snapshot(s)
        source["text"] += "new"
        self.assertTrue(fact_packet.verify(p, source, fact_packet.render(p)))

    def test_multiple_actors_clubs_negation_and_unknown_owner_go_to_review(self):
        for changes in ({"pids": {1, 2}}, {"teams": {"TOR", "MIN"}},
                        {"headline": "NHL Status Report"},
                        {"text": "Test Forward is not expected to rejoin the Toronto Maple Leafs on Saturday."},
                        {"text": "Test Forward is expected to rejoin the Minnesota Wild on Saturday."}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.extract(self.source(**changes)))

    def test_conflicting_return_dates_are_not_first_match_wins(self):
        s = self.source()
        s.text += " Test Forward is expected to rejoin the Toronto Maple Leafs on Sunday."
        self.assertIsNone(self.extract(s))

    def test_regular_jersey_alone_does_not_prove_a_return_to_games(self):
        s = self.source(text="Test Forward practiced in a regular jersey on Friday.")
        self.assertIsNone(self.extract(s))

    def test_rendered_fact_evidence_is_mandatory(self):
        s = self.source()
        p = self.extract(s)
        altered = copy.deepcopy(p)
        altered["claims"][0]["evidence"] = ""
        self.assertTrue(fact_packet.verify(altered, fact_packet.snapshot(s), fact_packet.render(altered)))


if __name__ == "__main__":
    unittest.main()
