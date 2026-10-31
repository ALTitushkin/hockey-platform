"""Регрессии потери постов при отказе модели, источника и Telegram."""
import tempfile
import unittest
from datetime import datetime, time, timezone
from pathlib import Path
from unittest.mock import patch

from news import publish, run, service, stories


class DeliveryTests(unittest.TestCase):
    def test_failed_delivery_after_deadline_keeps_retry_interval(self):
        now = datetime(2026, 10, 31, 13, tzinfo=timezone.utc)
        state = {"next_try": now.timestamp() + service.RETRY, "last_try": True}
        self.assertIsNone(service.due(now, state, time(9), time(12)))

    def test_saved_post_delivery_failure_is_retryable(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)):
            publish.save_draft("2026-10-31", "text", [], "test", kind="league")
            with patch.dict("os.environ", {"NEWS_AUTO_PUBLISH": "1"}), \
                    patch.object(publish, "auto_publish", side_effect=[(False, "timeout"), (True, "ok")]), \
                    patch.object(run, "load", side_effect=AssertionError("must not rebuild")):
                self.assertEqual(run.build_league("2026-10-31", True), "retry")
                self.assertEqual(run.build_league("2026-10-31", True), "ok")

    def test_story_model_failure_remains_unseen(self):
        self.story_failure("model")

    def test_story_source_failure_remains_unseen(self):
        self.story_failure("source")

    def test_story_delivery_failure_reuses_saved_draft(self):
        self.story_failure("delivery")

    def story_failure(self, failure):
        now = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
        s = stories.Story("event", "event", "Player signs contract", "", now, "signing", set(), set(), True)
        with tempfile.TemporaryDirectory() as tmp, patch.object(publish, "OUT", Path(tmp)), \
                patch.object(stories, "STATE", Path(tmp) / "state.json"), \
                patch.object(stories, "parse_item", return_value=s), \
                patch.object(stories, "body_text", return_value=("source", {})) as body, \
                patch.object(stories, "card", return_value=Path(tmp) / "card.png"), \
                patch.object(stories, "check", return_value=([], [])):
            if failure == "source":
                body.side_effect = RuntimeError("offline")
            write = unittest.mock.Mock(return_value=(None, "fake", []) if failure == "model"
                                       else ("Heading\n\nBody", "fake", []))
            deliver = unittest.mock.Mock(return_value=(False, "offline"))
            args = (now, lambda url: {"items": [{}]}, {}, {}, lambda p, r: {}, write,
                    lambda: [], deliver, lambda text: None)
            stories.process(*args)
            self.assertNotIn("event", stories.load_state(now)["seen"])
            if failure == "delivery":
                write.reset_mock()
                deliver.return_value = (True, "ok")
                stories.process(*args)
                write.assert_not_called()
                self.assertIn("event", stories.load_state(now)["seen"])


if __name__ == "__main__":
    unittest.main()
