"""Adversarial contracts for evidence, queue continuity and bounded revision polling."""

import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from news import editorial_queue, fact_packet, source_watch


class EvidenceQA(unittest.TestCase):
    def source(self):
        return SimpleNamespace(eid="one", kind="return", link="https://www.nhl.com/news/one",
                               headline="Forward expected back", pids={1}, teams={"TOR"},
                               en={1: "Test Forward"}, date=datetime(2026, 11, 6, tzinfo=timezone.utc),
                               text="Test Forward is expected to rejoin the Toronto Maple Leafs on Saturday.")

    def test_evidence_span_cannot_authorize_changed_semantics(self):
        source = self.source()
        packet = fact_packet.extract(source, {"1": {"ru": "Тестовый Игрок"}},
                                     {"TOR": "Торонто"}, {"TOR": ("Toronto", "Maple Leafs")})
        self.assertIsNotNone(packet)
        for field, value in (("date", "2026-12-25"), ("subject", 99), ("modality", "confirmed")):
            with self.subTest(field=field):
                altered = copy.deepcopy(packet)
                altered["claims"][0][field] = value
                self.assertTrue(fact_packet.verify(altered, fact_packet.snapshot(source), fact_packet.render(altered)))

    def test_malformed_claims_are_rejected_with_reason_instead_of_crashing(self):
        source = self.source()
        packet = fact_packet.extract(source, {"1": {"ru": "Тестовый Игрок"}},
                                     {"TOR": "Торонто"}, {"TOR": ("Toronto", "Maple Leafs")})
        for claims in ([], None, [{"evidence": source.text, "kind": "unknown"}]):
            with self.subTest(claims=claims):
                malformed = {**packet, "claims": claims}
                self.assertTrue(fact_packet.verify(malformed, fact_packet.snapshot(source), "text"))

    def test_stale_historical_expected_return_is_not_redated_to_next_week(self):
        source = self.source()
        source.text = ("Last season, Test Forward is expected to rejoin the Toronto Maple Leafs on Saturday.")
        packet = fact_packet.extract(source, {"1": {"ru": "Тестовый Игрок"}},
                                     {"TOR": "Торонто"}, {"TOR": ("Toronto", "Maple Leafs")})
        self.assertIsNone(packet, "historical context cannot become a current-week forecast")

    def test_expected_return_to_practice_does_not_become_return_to_lineup(self):
        source = self.source()
        source.text = "Test Forward is expected to rejoin the Toronto Maple Leafs for practice on Saturday."
        packet = fact_packet.extract(source, {"1": {"ru": "Тестовый Игрок"}},
                                     {"TOR": "Торонто"}, {"TOR": ("Toronto", "Maple Leafs")})
        self.assertIsNone(packet, "expected team practice is not evidence of expected game participation")


class RevisionBudgetQA(unittest.TestCase):
    def test_malformed_watch_entry_does_not_block_other_sources(self):
        now = datetime(2026, 11, 6, tzinfo=timezone.utc)
        state = {"source_watch": {"bad": None, "invalid-time": {"checked": "broken", "until": "broken"}}}
        story = SimpleNamespace(eid="good", headline="News", text="first", date=now)
        source_watch.remember(state, {"_entityId": "good"}, story, now)
        calls = []
        source_watch.prepare([], state, now + timedelta(minutes=16), lambda raw: story,
                             lambda s: (calls.append(s.eid) or "first", {}))
        self.assertEqual(calls, ["good"])

    def test_poll_budget_rotates_and_does_not_starve_ninth_source(self):
        now = datetime(2026, 11, 6, tzinfo=timezone.utc)
        state = {}
        for n in range(9):
            story = SimpleNamespace(eid=str(n), headline="News", text="body", date=now)
            source_watch.remember(state, {"_entityId": str(n)}, story, now)
        calls = []
        def parse(raw):
            return SimpleNamespace(eid=raw["_entityId"], headline="News", date=now)
        def fetch(story):
            calls.append(story.eid)
            return "body", {}
        source_watch.prepare([], state, now + timedelta(minutes=16), parse, fetch)
        self.assertEqual(len(calls), 8)
        source_watch.prepare([], state, now + timedelta(minutes=32), parse, fetch)
        self.assertIn("8", calls)
        self.assertLessEqual(len(calls), 16)

    def test_watch_does_not_collapse_multiple_items_without_entity_id(self):
        items = [{"id": "first"}, {"id": "second"}]
        actual, cached = source_watch.prepare(items, {}, datetime(2026, 11, 6, tzinfo=timezone.utc), None, None)
        self.assertEqual(actual, items)
        self.assertEqual(cached, {})


class QueueContinuityQA(unittest.TestCase):
    def test_unknown_delivery_survives_restart_and_resync(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "editorial.sqlite3"
            draft = {"text": "draft", "issues": [], "data": {"auto": True}}
            queue = editorial_queue.Queue(path)
            revision = queue.sync("one", draft)
            queue.mark("one", revision, "delivery_unknown")
            queue.close()
            queue = editorial_queue.Queue(path)
            try:
                queue.sync("one", draft)
                self.assertEqual(queue.status("one"), "delivery_unknown")
            finally:
                queue.close()


if __name__ == "__main__":
    unittest.main()
