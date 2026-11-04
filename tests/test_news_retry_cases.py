"""Сценарии повторной доставки без сети и токенов."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from news import llm, publish, run, stories


class RetryCases(unittest.TestCase):
    def test_model_failure_retries_after_story_disappears_from_feed(self):
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        story = stories.Story("event", "event", "Player signs contract", "", now,
                              "signing", set(), set(), True)
        feed = {"items": [{"id": "event"}]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.object(stories, "STATE", Path(tmp) / "state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "body_text", return_value=("source", {})), \
                patch.object(stories, "card", return_value=Path(tmp) / "card.png"), \
                patch.object(stories, "check", return_value=([], [])):
            write = Mock(side_effect=[(None, "fake", []), ("Heading\n\nBody", "fake", [])])
            deliver = Mock(return_value=(True, "ok"))
            args = (lambda url: feed, {}, {}, lambda p, r: {}, write, lambda: [], deliver, lambda text: None)
            stories.process(now, *args)
            self.assertIn("event", stories.load_state(now)["pending_items"])
            feed["items"] = []
            later = now + timedelta(minutes=30)
            stories.process(later, *args)
            deliver.assert_called_once_with("2026-10-31", "story-event")
            state = stories.load_state(later)
            self.assertIn("event", state["seen"])
            self.assertNotIn("event", state["pending_items"])

    def test_two_status_reports_with_same_hero_keep_both_for_fact_review(self):
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        first = stories.Story("first", "first", "NHL Status Report: Hall could return for Hurricanes", "",
                              now, "return", set(), set(), True)
        second = stories.Story("second", "second", "NHL Status Report: Hall remains injured", "",
                               now + timedelta(minutes=1), "injury_minor", set(), set(), True)
        records = {"first": first, "second": second}
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.object(stories, "STATE", Path(tmp) / "state.json"), \
                patch.object(stories, "parse_item", side_effect=lambda raw: records[raw["id"]]), \
                patch.object(stories, "body_text", return_value=("source", {})), \
                patch.object(stories, "card", return_value=Path(tmp) / "card.png"), \
                patch.object(stories, "check", return_value=([], [])):
            deliver = Mock(return_value=(True, "ok"))
            write = Mock(return_value=("Heading\n\nBody", "fake", []))
            stories.process(now + timedelta(minutes=2),
                            lambda url: {"items": [{"id": "first"}, {"id": "second"}]},
                            {}, {}, lambda p, r: {}, write, lambda: [], deliver, lambda text: None)
            self.assertEqual(deliver.call_args_list, [unittest.mock.call("2026-10-31", "story-first"),
                                                      unittest.mock.call("2026-10-31", "story-second")])
            self.assertEqual(write.call_count, 2)
            self.assertIn("second", stories.load_state(now)["seen"])

    def test_partial_delivery_across_midnight_uses_original_draft(self):
        now = datetime(2026, 10, 31, 23, 59, tzinfo=timezone.utc)
        story = stories.Story("event", "event", "Player signs contract", "", now,
                              "signing", set(), set(), True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.object(stories, "STATE", Path(tmp) / "state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "body_text", return_value=("source", {})), \
                patch.object(stories, "card", return_value=Path(tmp) / "card.png"), \
                patch.object(stories, "check", return_value=([], [])):
            write = Mock(return_value=("Heading\n\nBody", "fake", []))
            calls = []

            def deliver(msk, kind):
                calls.append(msk)
                path = publish.draft_path(msk, kind)
                draft = json.loads(path.read_text(encoding="utf-8"))
                if len(calls) == 1:
                    draft["published"] = ["tg"]
                    path.write_text(json.dumps(draft), encoding="utf-8")
                    return False, "max failed"
                self.assertEqual(draft["published"], ["tg"])
                return True, "max delivered"

            def process(at):
                return stories.process(at, lambda url: {"items": [{}]}, {}, {}, lambda p, r: {},
                                       write, lambda: [], deliver, lambda text: None)

            process(now)
            process(now + timedelta(minutes=2))
            self.assertEqual(calls, ["2026-10-31", "2026-10-31"])
            self.assertEqual(write.call_count, 1)
            self.assertIn("event", stories.load_state(now + timedelta(minutes=2))["seen"])

    def test_model_outage_retries_without_repeated_owner_notifications(self):
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        story = stories.Story("event", "event", "Player signs contract", "", now,
                              "signing", set(), set(), True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.object(stories, "STATE", Path(tmp) / "state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "body_text", return_value=("source", {})):
            notify = Mock()
            write = Mock(return_value=(None, "fake", []))
            deliver = Mock()
            for minutes in (0, 15, 30, 359, 720):
                stories.process(now + timedelta(minutes=minutes), lambda url: {"items": [{}]},
                                {}, {}, lambda p, r: {}, write, lambda: [], deliver, notify)
            self.assertEqual(write.call_count, 4)
            self.assertEqual(notify.call_count, 2)
            deliver.assert_not_called()
            self.assertNotIn("event", stories.load_state(now + timedelta(hours=12))["seen"])

    def test_source_excerpt_keeps_full_late_paragraph_about_our_player(self):
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        story = stories.Story("event", "event", "Player signs contract", "", now,
                              "signing", set(), set(), True)
        needed = "Igor Shesterkin is injured. " + "Medical update. " * 50
        story.text = "Opening paragraph.\n\n" + "Unrelated material. " * 300 + "\n\n" + needed
        story.en = {4: "Igor Shesterkin"}
        self.assertGreater(story.text.index("Igor Shesterkin"), 5000)
        excerpt = stories.source_excerpt(story, {4})
        self.assertIn(needed, excerpt)
        self.assertIn("Opening paragraph.", excerpt)

    def test_editorial_skip_notifies_without_closing_story(self):
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        story = stories.Story("event", "event", "Player signs contract", "", now,
                              "signing", set(), set(), True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.object(stories, "STATE", Path(tmp) / "state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "body_text", return_value=("source", {})):
            notify, deliver = Mock(), Mock()

            def write(prompt, accept):
                return llm.ask(prompt, accept, stories.clean, chain="fake",
                               providers={"fake": lambda text: "SKIP: нет нового события"})

            stories.process(now, lambda url: {"items": [{}]}, {}, {}, lambda p, r: {},
                            write, lambda: [], deliver, notify)
            self.assertNotIn("event", stories.load_state(now)["seen"])
            self.assertIn("event", stories.load_state(now)["pending_items"])
            notify.assert_called_once()
            self.assertIn("Инфоповод без поста", notify.call_args.args[0])
            deliver.assert_not_called()

    def test_rejected_regular_post_is_not_redelivered(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)):
            publish.save_draft("2026-10-31", "text", [], "test", kind="league")
            publish.reject("2026-10-31", "league")
            with patch.object(publish, "review") as review, patch.object(publish, "auto_publish") as auto:
                self.assertEqual(run.deliver_draft("2026-10-31", "league"), "ok")
                review.assert_not_called()
                auto.assert_not_called()

    def test_guard_review_failure_stays_retryable_and_never_auto_publishes(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)):
            publish.save_draft("2026-10-31", "text", ["unknown number"], "test", kind="league")
            with patch.dict("os.environ", {"NEWS_AUTO_PUBLISH": "1"}), \
                    patch.object(publish, "review", side_effect=[(False, "offline"), (True, "ok")]), \
                    patch.object(publish, "auto_publish") as auto:
                self.assertEqual(run.deliver_draft("2026-10-31", "league"), "retry")
                self.assertEqual(run.deliver_draft("2026-10-31", "league"), "guard")
                auto.assert_not_called()


if __name__ == "__main__":
    unittest.main()
