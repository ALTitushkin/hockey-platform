"""Контракты теневого дедупа: версии фактов сохраняются, публикация не вызывается."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from news.source_dedup import Event, Ledger, canonical_url, fingerprint


class CanonicalTests(unittest.TestCase):
    def test_tracking_parameters_and_fragment_do_not_make_a_new_document(self):
        self.assertEqual(canonical_url(" HTTPS://NHL.COM/news/x?article=7&utm_source=tg&FBCLID=abc#top "),
                         "https://nhl.com/news/x?article=7")

    def test_meaningful_query_and_path_are_preserved(self):
        self.assertNotEqual(canonical_url("https://nhl.com/news?id=7"),
                            canonical_url("https://nhl.com/news?id=8"))
        self.assertNotEqual(canonical_url("https://nhl.com/News"), canonical_url("https://nhl.com/news"))

    def test_whitespace_case_and_unicode_do_not_make_new_text(self):
        self.assertEqual(fingerprint("  Kochetkov\nWON\t９ games. "), fingerprint("kochetkov won 9 games."))

    def test_numbers_and_negation_are_not_erased(self):
        self.assertNotEqual(fingerprint("He won 9 games."), fingerprint("He won 10 games."))
        self.assertNotEqual(fingerprint("He will play."), fingerprint("He will not play."))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "shadow.sqlite"
        self.ledger = Ledger(self.path)

    def tearDown(self):
        self.ledger.close()
        self.tmp.cleanup()

    def observe(self, item="1", text="Kochetkov won 9 games.", source="nhl", url=None, event=None):
        return self.ledger.observe(source, item, url or f"https://{source}.example/news/{item}", text, event)

    def event(self, status="expected", term="two weeks", action="injury", episode="2026-11-01"):
        return Event(("player:8481611",), action, episode, {"status": status, "term": term})

    def test_identical_text_from_a_new_episode_after_weeks_is_not_suppressed(self):
        self.ledger.clock = lambda: 100
        first = self.observe()
        self.ledger.clock = lambda: 100 + 14 * 86400
        later = self.observe(item="different", source="ahl")
        self.assertEqual(later.kind, "new")
        self.assertNotEqual(first.cluster_id, later.cluster_id)

    def test_same_guid_same_text_and_tracking_url_are_duplicates(self):
        first = self.observe(url="https://nhl.example/story?utm_source=a")
        again = self.observe(url="https://nhl.example/story?utm_source=b")
        other_id = self.observe(item="2", url="https://nhl.example/story?fbclid=a")
        self.assertEqual(first.kind, "new")
        self.assertEqual((again.kind, other_id.kind), ("duplicate", "duplicate"))
        self.assertEqual({first.cluster_id, again.cluster_id, other_id.cluster_id}, {first.cluster_id})

    def test_exact_text_across_sources_clusters_without_model(self):
        a = self.observe()
        b = self.observe(source="ahl", text="  KOCHETKOV\nwon 9 games. ")
        self.assertEqual((b.kind, b.cluster_id), ("duplicate", a.cluster_id))

    def test_same_guid_and_same_url_preserve_changed_versions(self):
        a = self.observe()
        b = self.observe(text="Kochetkov won 10 games.", url="https://nhl.example/new-url")
        c = self.observe(item="new-guid", text="Kochetkov won 11 games.", url="https://nhl.example/new-url")
        self.assertEqual((b.kind, c.kind), ("update", "update"))
        self.assertEqual({a.cluster_id, b.cluster_id, c.cluster_id}, {a.cluster_id})
        self.assertEqual(self.observe(text="Kochetkov won 9 games.").kind, "duplicate")

    def test_numeric_and_negation_changes_remain_updates(self):
        self.observe(text="He will play in 2 weeks.")
        self.assertEqual(self.observe(text="He will play in 3 weeks.").kind, "update")
        self.assertEqual(self.observe(text="He will not play in 3 weeks.").kind, "update")

    def test_old_url_remains_associated_when_source_changes_guid_and_url(self):
        first = self.observe(url="https://nhl.example/original", text="Initial report")
        self.observe(url="https://nhl.example/renamed", text="Second version")
        later = self.observe(item="replacement-guid", url="https://nhl.example/original", text="Third version")
        self.assertEqual((later.kind, later.cluster_id), ("update", first.cluster_id))

    def test_same_guid_is_scoped_to_source(self):
        a = self.observe(text="First story")
        b = self.observe(source="ahl", text="Unrelated story")
        self.assertEqual(b.kind, "new")
        self.assertNotEqual(a.cluster_id, b.cluster_id)

    def test_semantic_same_facts_duplicate_despite_different_words(self):
        a = self.observe(event=self.event())
        b = self.observe(source="ahl", text="Different wording of the same injury", event=self.event())
        self.assertEqual((b.kind, b.cluster_id), ("duplicate", a.cluster_id))

    def test_confirmed_status_and_changed_term_are_versions_even_when_text_unchanged(self):
        a = self.observe(event=self.event())
        b = self.observe(event=self.event(status="confirmed"))
        c = self.observe(event=self.event(status="confirmed", term="four weeks"))
        self.assertEqual((b.kind, c.kind), ("update", "update"))
        self.assertEqual({a.cluster_id, b.cluster_id, c.cluster_id}, {a.cluster_id})

    def test_changed_action_and_episode_are_new_events_even_on_same_page(self):
        a = self.observe(event=self.event())
        b = self.observe(event=self.event(action="return"))
        c = self.observe(event=self.event(episode="2026-11-10"))
        self.assertEqual((a.kind, b.kind, c.kind), ("new", "new", "new"))
        self.assertEqual(len({a.cluster_id, b.cluster_id, c.cluster_id}), 3)

    def test_event_entities_order_and_fact_key_order_are_irrelevant(self):
        a = self.observe(event=Event(("player:1", "team:2"), "trade", "deal-1", {"a": 1, "b": 2}))
        b = self.observe(source="ahl", event=Event(("team:2", "player:1"), "trade", "deal-1", {"b": 2, "a": 1}))
        self.assertEqual((b.kind, b.cluster_id), ("duplicate", a.cluster_id))

    def test_reopening_keeps_versions_and_event_status(self):
        first = self.observe(event=self.event())
        self.observe(event=self.event(status="confirmed"))
        self.ledger.close()
        self.ledger = Ledger(self.path)
        again = self.observe(source="ahl", event=self.event(status="confirmed"))
        older = self.observe(source="ahl", event=self.event())
        self.assertEqual((again.kind, older.kind), ("duplicate", "duplicate"))
        self.assertEqual(again.cluster_id, first.cluster_id)

    def test_observation_has_no_publication_side_effect(self):
        with patch("news.publish.publish") as publish, patch("news.publish.tg_call") as telegram:
            self.assertEqual(self.observe().kind, "new")
            self.assertEqual(self.observe().kind, "duplicate")
        publish.assert_not_called()
        telegram.assert_not_called()

    def test_incomplete_event_cannot_suppress_a_story(self):
        with self.assertRaises(ValueError):
            self.observe(event=Event((), "injury", "2026-11-01", {"status": "expected"}))
        self.assertEqual(self.observe().kind, "new")


if __name__ == "__main__":
    unittest.main()
