"""Сценарии повторной доставки без сети и токенов."""

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from news import publish, run, stories


class RetryCases(unittest.TestCase):
    def test_unsupported_story_is_saved_as_source_task_without_model_retry(self):
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        story = stories.Story("event", "event", "Player signs contract", "", now,
                              "signing", set(), set(), True)
        feed = {"items": [{"id": "event"}]}
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.object(stories, "STATE", Path(tmp) / "state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "body_text", return_value=("source", {})), \
                patch.object(stories, "check", return_value=([], [])):
            write = Mock(side_effect=AssertionError("unsupported stories are not paraphrased"))
            deliver = Mock(return_value=(True, "ok"))
            args = (lambda url: feed, {}, {}, lambda p, r: {}, write, lambda: [], deliver, lambda text: None)
            stories.process(now, *args)
            draft = json.loads(publish.draft_path("2026-10-31", "story-event").read_text(encoding="utf-8"))
            self.assertTrue(draft["data"]["editorial_task"])
            self.assertIsNone(draft["card"])
            feed["items"] = []
            later = now + timedelta(minutes=30)
            stories.process(later, *args)
            self.assertEqual(deliver.call_count, 1)
            state = stories.load_state(later)
            self.assertIn("event", state["seen"])
            self.assertNotIn("event", state["pending_items"])
            write.assert_not_called()

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
                patch.object(stories, "check", return_value=([], [])):
            deliver = Mock(return_value=(True, "ok"))
            write = Mock(side_effect=AssertionError("unsupported stories are not paraphrased"))
            stories.process(now + timedelta(minutes=2),
                            lambda url: {"items": [{"id": "first"}, {"id": "second"}]},
                            {}, {}, lambda p, r: {}, write, lambda: [], deliver, lambda text: None)
            self.assertEqual(deliver.call_args_list, [unittest.mock.call("2026-10-31", "story-first"),
                                                      unittest.mock.call("2026-10-31", "story-second")])
            write.assert_not_called()
            self.assertIn("second", stories.load_state(now)["seen"])

    def test_partial_delivery_across_midnight_uses_original_draft(self):
        now = datetime(2026, 10, 31, 23, 59, tzinfo=timezone.utc)
        story = stories.Story("event", "event", "Player signs contract", "", now,
                              "signing", set(), set(), True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.object(stories, "STATE", Path(tmp) / "state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "body_text", return_value=("source", {})), \
                patch.object(stories, "check", return_value=([], [])):
            write = Mock(side_effect=AssertionError("unsupported stories are not paraphrased"))
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
            write.assert_not_called()
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
            write = Mock(side_effect=AssertionError("unsupported stories are not paraphrased"))
            deliver = Mock(return_value=(True, "ok"))
            for minutes in (0, 15, 30, 359, 720):
                stories.process(now + timedelta(minutes=minutes), lambda url: {"items": [{}]},
                                {}, {}, lambda p, r: {}, write, lambda: [], deliver, notify)
            write.assert_not_called()
            self.assertEqual(deliver.call_count, 1)
            self.assertEqual(notify.call_count, 0)
            self.assertIn("event", stories.load_state(now + timedelta(hours=12))["seen"])

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

    def test_unsupported_story_is_actionable_without_model_skip(self):
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        story = stories.Story("event", "event", "Player signs contract", "", now,
                              "signing", set(), set(), True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.object(stories, "STATE", Path(tmp) / "state.json"), \
                patch.object(stories, "parse_item", return_value=story), \
                patch.object(stories, "body_text", return_value=("source", {})):
            notify, deliver = Mock(), Mock(return_value=(True, "ok"))

            write = Mock(side_effect=AssertionError("unsupported stories are not paraphrased"))

            stories.process(now, lambda url: {"items": [{}]}, {}, {}, lambda p, r: {},
                            write, lambda: [], deliver, notify)
            self.assertIn("event", stories.load_state(now)["seen"])
            self.assertNotIn("event", stories.load_state(now)["pending_items"])
            draft = json.loads(publish.draft_path("2026-10-31", "story-event").read_text(encoding="utf-8"))
            self.assertTrue(draft["data"]["editorial_task"])
            write.assert_not_called()
            notify.assert_not_called()
            deliver.assert_called_once()

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

