"""Source revisions survive feed disappearance without repeated generation on unchanged content."""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from news import source_watch


class SourceWatch(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 6, 20, tzinfo=timezone.utc)
        self.raw = {"_entityId": "original", "headline": "News"}
        self.state = {}
        self.parse = lambda raw: SimpleNamespace(eid=raw["_entityId"], headline=raw["headline"],
                                                text="first", date=self.now)
        source_watch.remember(self.state, self.raw, self.parse(self.raw), self.now)

    def test_changed_document_produces_new_identity_even_after_leaving_feed(self):
        items, cached = source_watch.prepare([], self.state, self.now + timedelta(minutes=16),
                                             self.parse, lambda s: ("updated", {1: "Name"}))
        self.assertEqual(len(items), 1)
        self.assertNotEqual(items[0]["_entityId"], "original")
        self.assertEqual(items[0]["_editorial_origin"], "original")
        self.assertEqual(cached[items[0]["_entityId"]][0], "updated")

    def test_unchanged_document_does_not_reopen_seen_item(self):
        items, cached = source_watch.prepare([self.raw], self.state, self.now + timedelta(minutes=16),
                                             self.parse, lambda s: ("first", {}))
        self.assertEqual(items, [self.raw])
        self.assertEqual(cached, {})

    def test_failed_or_empty_read_does_not_replace_last_good_hash(self):
        for mode in ("empty", "failed"):
            with self.subTest(mode=mode):
                before = self.state["source_watch"]["original"]["hash"]
                def fetch(s):
                    if mode == "failed":
                        raise RuntimeError("offline")
                    return "", {}
                source_watch.prepare([], self.state, self.now + timedelta(hours=2), self.parse, fetch)
                self.assertEqual(self.state["source_watch"]["original"]["hash"], before)

    def test_expired_watch_has_no_requests(self):
        def fetch(s):
            self.fail("expired source must not be fetched")
        source_watch.prepare([], self.state, self.now + timedelta(days=3), self.parse, fetch)
        self.assertEqual(self.state["source_watch"], {})


if __name__ == "__main__":
    unittest.main()
