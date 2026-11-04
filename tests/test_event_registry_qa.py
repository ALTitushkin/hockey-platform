"""Offline publication/restart regressions for typed event revisions."""

import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from news import event_registry, publish, stories


class EventRegistryQA(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = Path(self.tmp.name)
        self.scope = patch.object(publish, "OUT", self.out)
        self.scope.start()
        self.addCleanup(self.scope.stop)
        self.env = patch.dict(os.environ, {"NEWS_CHANNEL": "@hockey_test"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.channel_patch = patch.object(publish, "channel_key", return_value="tg:-1001234567890")
        self.channel_patch.start()
        self.addCleanup(self.channel_patch.stop)
        self.story = stories.Story("a", "first", "Islanders sign Hutton to PTO", "",
                                   datetime(2026, 11, 3, tzinfo=timezone.utc), "signing", {1}, {"NYI"}, True,
                                   text="Hutton signed a PTO on Monday.")
        self.event = event_registry.extract(self.story)
        self.assertTrue(event_registry.complete(self.event))

    def draft(self, kind, event=None):
        return publish.save_draft("2026-11-03", "Хаттон подписал контракт", [], "offline", kind=kind,
                                  data={"event_revision": self.event if event is None else event, "slug": kind})

    def test_same_revision_in_two_articles_sends_once(self):
        self.draft("story-first")
        self.draft("story-followup")
        with patch.object(publish, "tg_send", return_value=(True, "message_id 50")) as send:
            self.assertTrue(publish.publish("2026-11-03", ["tg"], kind="story-first")[0])
            self.assertEqual(send.call_args.args[0], "-1001234567890")
            self.assertFalse(publish.publish("2026-11-03", ["tg"], kind="story-followup")[0])
            self.assertEqual(send.call_count, 1)

    def test_crash_after_ledger_success_recovers_json_without_resending(self):
        path = self.draft("story-first")
        db = event_registry.Registry(self.out / "event_registry.sqlite3")
        self.assertEqual(db.reserve(self.event, "tg:-1001234567890", path.name)[0], "new")
        db.finish(self.event, "tg:-1001234567890", True, [50])
        db.close()
        with patch.object(publish, "tg_send", side_effect=AssertionError("duplicate network send")):
            self.assertTrue(publish.publish("2026-11-03", ["tg"], kind="story-first")[0])
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["published"], ["tg"])
        self.assertEqual(stored["messages"]["tg"], [50])
        self.assertEqual(stored["channels"]["tg"], "@hockey_test")
        self.assertEqual(stored["event_receipts"]["tg"]["channel"], "tg:-1001234567890")

    def test_uncertain_transport_is_quarantined_across_restart(self):
        self.draft("story-first")
        with patch.object(publish, "tg_send", return_value=(False, "timeout")) as send:
            self.assertFalse(publish.publish("2026-11-03", ["tg"], kind="story-first")[0])
            ok, report = publish.publish("2026-11-03", ["tg"], kind="story-first")
            self.assertFalse(ok)
            self.assertIn("сверки", report[0])
            self.assertEqual(send.call_count, 1)

    def test_distinct_actor_or_phase_is_not_suppressed(self):
        self.draft("story-first")
        with patch.object(publish, "tg_send", return_value=(True, "message_id 50")) as send:
            self.assertTrue(publish.publish("2026-11-03", ["tg"], kind="story-first")[0])
            for kind, event in (("story-other", {**self.event, "actors": [2]}),
                                ("story-contract", {**self.event, "phase": "standard", "facts": {"years": 1}})):
                self.draft(kind, event)
                self.assertTrue(publish.publish("2026-11-03", ["tg"], kind=kind)[0])
            self.assertEqual(send.call_count, 3)

    def test_explicit_fact_change_is_a_new_revision(self):
        self.draft("story-first")
        with patch.object(publish, "tg_send", return_value=(True, "message_id 50")):
            self.assertTrue(publish.publish("2026-11-03", ["tg"], kind="story-first")[0])
            update = copy.deepcopy(self.event)
            update["facts"]["years"] = 2
            self.draft("story-update", update)
            self.assertTrue(publish.publish("2026-11-03", ["tg"], kind="story-update")[0])

    def test_partial_revision_is_kept_for_review_not_silently_classified_duplicate(self):
        db = event_registry.Registry(self.out / "event_registry.sqlite3")
        try:
            db.reserve(self.event, "tg:-1001234567890", "old")
            db.finish(self.event, "tg:-1001234567890", True, [50])
            incomplete = {**self.event, "complete": False, "reasons": ["дата неизвестна"]}
            self.assertEqual(db.classify(incomplete)["status"], "review")
        finally:
            db.close()

    def test_uncertain_publication_is_not_evidence_of_confirmed_duplicate(self):
        db = event_registry.Registry(self.out / "event_registry.sqlite3")
        try:
            db.reserve(self.event, "tg:-1001234567890", "old")
            db.finish(self.event, "tg:-1001234567890", False, [])
            decision = db.classify(self.event)
            self.assertEqual(decision["status"], "review", "Unknown delivery requires explicit reconciliation")
        finally:
            db.close()

    def process_story(self, story, write):
        names = {"1": {"ru": "Бен Хаттон", "surname": "Хаттон", "status": "confirmed"}}
        with (
            patch.object(stories, "STATE", self.out / "stories_state.json"),
            patch.object(stories, "parse_item", return_value=story),
            patch.object(stories, "select", return_value=[story]),
            patch.object(stories, "body_text", return_value=(story.text, {1: "Ben Hutton"})),
            patch.object(stories, "check", return_value=([], [])),
            patch.object(stories, "goalie_stats", return_value=[]),
            patch.object(stories, "card", return_value=self.out / "none.png"),
        ):
            def deliver(msk, kind):
                d = json.loads(publish.draft_path(msk, kind).read_text(encoding="utf-8"))
                return publish.publish(msk, ["tg"], kind=kind) if d["data"]["auto"] else (True, "review")
            return stories.process(story.date, lambda url: {"items": [{}]}, {}, {"NYI": "Айлендерс"},
                                   lambda pids, reg: names, write, lambda: [], deliver, lambda text: None)

    @staticmethod
    def accepted_write(prompt, accept):
        body = "Бен Хаттон подписал пробный контракт\n\nЗащитник присоединился к Айлендерс."
        assert not accept(body)
        return body, "offline", []

    def test_process_deduplicates_published_revision_after_first_source_leaves_feed(self):
        with patch.object(publish, "tg_send", return_value=(True, "message_id 50")) as send:
            self.process_story(self.story, self.accepted_write)
            later = copy.deepcopy(self.story)
            later.eid, later.slug = "b", "followup"
            write = Mock(side_effect=AssertionError("same facts must not call model again"))
            self.process_story(later, write)
            write.assert_not_called()
            self.assertEqual(send.call_count, 1)
            self.assertFalse(publish.draft_path("2026-11-03", "story-b").exists())

    def test_process_preserves_partial_followup_as_review_even_with_published_actor(self):
        with patch.object(publish, "tg_send", return_value=(True, "message_id 50")) as send:
            self.process_story(self.story, self.accepted_write)
            later = copy.deepcopy(self.story)
            later.eid, later.slug = "b", "followup"
            later.text = "Hutton signed a PTO. Conditions are being discussed."
            self.process_story(later, self.accepted_write)
            draft = json.loads(publish.draft_path("2026-11-03", "story-b").read_text(encoding="utf-8"))
            self.assertFalse(draft["data"]["auto"])
            self.assertEqual(draft["data"]["event_decision"]["status"], "review")
            self.assertEqual(send.call_count, 1)

    def test_database_rebuild_uses_frozen_receipt_not_changed_draft_facts(self):
        path = self.draft("story-first")
        with patch.object(publish, "tg_send", return_value=(True, "message_id 50")):
            self.assertTrue(publish.publish("2026-11-03", ["tg"], kind="story-first")[0])
        updated = copy.deepcopy(self.event)
        updated["phase"] = "standard"
        updated["facts"] = {"years": 1}
        publish.save_draft("2026-11-03", "Новые условия контракта", [], "rebuilt", kind="story-first",
                           data={"event_revision": updated, "slug": "story-first"})
        stored = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(stored["event_receipts"]["tg"]["event"], self.event)
        self.assertEqual(stored["data"]["event_revision"], updated)
        rebuilt_path = self.out / "fresh-rebuild.sqlite3"
        real_registry = event_registry.Registry
        db = real_registry(rebuilt_path)
        try:
            db.sync_archive(self.out)
            self.assertEqual(db.classify(self.event)["status"], "duplicate")
            self.assertNotEqual(db.classify(updated)["status"], "duplicate")
        finally:
            db.close()
        self.draft("story-new-version", updated)
        self.draft("story-copy-new-version", updated)
        with (
            patch.object(event_registry, "Registry", side_effect=lambda path: real_registry(rebuilt_path)),
            patch.object(publish, "tg_send", return_value=(True, "message_id 51")) as send,
        ):
            self.assertTrue(publish.publish("2026-11-03", ["tg"], kind="story-new-version")[0])
            self.assertFalse(publish.publish("2026-11-03", ["tg"], kind="story-copy-new-version")[0])
            self.assertEqual(send.call_count, 1)

    def test_unfrozen_archive_does_not_claim_new_fact_publication(self):
        path = self.draft("story-old-format")
        stored = json.loads(path.read_text(encoding="utf-8"))
        stored.update(published=["tg"], messages={"tg": [50]}, channels={"tg": "@hockey_test"})
        path.write_text(json.dumps(stored), encoding="utf-8")
        db = event_registry.Registry(self.out / "fresh-rebuild.sqlite3")
        try:
            db.sync_archive(self.out)
            self.assertNotEqual(db.classify(self.event)["status"], "duplicate")
        finally:
            db.close()


class ChannelKeyQA(unittest.TestCase):
    def test_username_and_numeric_channel_share_one_key_and_resolution_is_cached(self):
        post = Mock(return_value={"ok": True, "result": {"id": -1001234567890, "type": "channel"}})
        with patch.dict(publish.CHANNEL_IDS, {}, clear=True), patch.dict(os.environ, {"NEWS_CHANNEL": "@hockey_test"}):
            expected = "tg:-1001234567890"
            self.assertEqual(publish.channel_key("tg", post), expected)
            self.assertEqual(publish.channel_key("tg", post), expected)
            self.assertEqual(post.call_count, 1)
            with patch.dict(os.environ, {"NEWS_CHANNEL": "-1001234567890"}):
                self.assertEqual(publish.channel_key("tg", post), expected)
                self.assertEqual(post.call_count, 1)

    def test_invalid_getchat_response_cannot_acquire_a_publication_identity(self):
        responses = ({"ok": False}, {"ok": True, "result": None},
                     {"ok": True, "result": {"id": True, "type": "channel"}},
                     {"ok": True, "result": {"id": -1001234567890, "type": "group"}},
                     {"ok": True, "result": {"id": 0, "type": "channel"}})
        for response in responses:
            with (
                self.subTest(response=response),
                patch.dict(publish.CHANNEL_IDS, {}, clear=True),
                patch.dict(os.environ, {"NEWS_CHANNEL": "@hockey_test"}),
                self.assertRaises(RuntimeError),
            ):
                publish.channel_key("tg", Mock(return_value=response))


if __name__ == "__main__":
    unittest.main()
